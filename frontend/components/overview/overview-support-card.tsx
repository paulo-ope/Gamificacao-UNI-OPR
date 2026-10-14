"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import { OverviewProgress, OverviewTile } from "@/components/overview/overview-layout-parts";
import { MultiSelect } from "@/components/ui/multi-select";
import { secondsLabel } from "@/lib/format-duration";
import { formatDateTime, formatInteger, formatIsoDate, formatPercent } from "@/lib/format";
import type { SupportOpaFilterOption, SupportOpaMetricComparison, SupportOpaOverview } from "@/lib/types";

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

/** Texto de apoio do TMA efetivo: avisa quando só parte dos encerrados já foi calculada (o histórico
 *  é preenchido aos poucos), senão mostra a variação contra o período anterior. */
function tmaEffectiveHint(data: SupportOpaOverview | null) {
  const coverage = data?.tma_effective_coverage;
  if (coverage && coverage.total > 0 && coverage.count < coverage.total) {
    return `${formatInteger(coverage.count)} de ${formatInteger(coverage.total)} encerrados (atend. com humano)`;
  }
  return changeHint(data?.average_tma_effective_seconds, "seconds");
}

/**
 * Bloco macro do Suporte Interno. Usa o mesmo `/support/opa/overview` da tela do módulo (nenhuma
 * métrica nova, nenhuma conta refeita aqui) e só o período da Visão Geral - os filtros de O.S.
 * (modelo de equipe, filial, colaborador) não existem no domínio de atendimentos, então aplicá-los
 * aqui daria a falsa impressão de um número recortado. O departamento, sim, é do domínio de
 * atendimentos: o seletor do cabeçalho escreve no mesmo `support_department` da barra de filtros.
 */
export function OverviewSupportCard({
  data,
  state,
  dateFrom,
  dateTo,
  departmentOptions,
  departmentValues,
  onDepartmentChange,
}: {
  data: SupportOpaOverview | null;
  state?: OverviewBlockState;
  dateFrom: string;
  dateTo: string;
  departmentOptions: SupportOpaFilterOption[];
  departmentValues: string[];
  onDepartmentChange: (values: string[]) => void;
}) {
  const total = data?.total_attendances.current ?? null;
  const open = data?.open_attendances.current ?? null;
  const closed = data?.closed_attendances.current ?? null;
  return (
    <OverviewBlock
      eyebrow="Suporte Interno"
      title="Atendimentos do período"
      subtitle={
        departmentValues.length
          ? "Período e departamento selecionado - os filtros de O.S. não se aplicam a atendimentos."
          : "Todos os departamentos do OPA - escolha um departamento para recortar. Os filtros de O.S. não se aplicam."
      }
      actions={
        <div className="flex items-center gap-3">
          {/* Mesmo estado `support_department` da barra de filtros: escolher aqui ou lá dá o mesmo recorte. */}
          <MultiSelect<SupportOpaFilterOption>
            className="h-8 w-56 text-[11px]"
            values={departmentValues}
            options={departmentOptions}
            getValue={(option) => option.value}
            formatOption={(option) => option.label}
            placeholder="Todos os departamentos"
            ariaLabel="Departamento do Suporte Interno"
            onChange={onDepartmentChange}
          />
          <Link
            href="/suporte"
            className="inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold text-uni-royal hover:underline"
          >
            Abrir módulo
            <ArrowUpRight className="h-3 w-3" />
          </Link>
        </div>
      }
      state={state}
      deniedLabel="Seu perfil não tem acesso ao Suporte Interno."
    >
      <div className="grid grid-cols-2 gap-2.5 2xl:grid-cols-5">
        <OverviewTile
          label="Atendimentos"
          value={formatInteger(total)}
          accent="blue"
          sub={changeHint(data?.total_attendances, "count")}
        />
        <OverviewTile
          label="Finalizados"
          value={formatInteger(closed)}
          accent="teal"
          sub={`Taxa de encerramento ${formatPercent(data?.closure_rate.current ?? null)}`}
        />
        <OverviewTile label="Em aberto" value={formatInteger(open)} accent="amber" sub="agora" />
        <OverviewTile
          label="Tempo Médio de Atendimento - Humano"
          value={<span className="text-[1.15rem]">{secondsLabel(data?.average_tma_effective_seconds.current ?? null)}</span>}
          accent="violet"
          sub={tmaEffectiveHint(data)}
        />
        <OverviewTile
          label="TMR Geral · TMR Humano"
          value={
            <span className="text-[1.15rem]">
              {secondsLabel(data?.average_tmr_effective_seconds.current ?? null)} · {secondsLabel(data?.average_tmr_human_live_seconds.current ?? null)}
            </span>
          }
          accent="violet"
          sub={`${changeHint(data?.average_tmr_effective_seconds, "seconds")} (geral inclui o bot)`}
        />
      </div>
      <OverviewProgress
        leftLabel="Finalizados"
        leftValue={formatPercent(data?.closure_rate.current ?? null)}
        rightLabel="Não finalizados"
        rightValue={formatInteger(open)}
        percent={data?.closure_rate.current ?? null}
      />
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
