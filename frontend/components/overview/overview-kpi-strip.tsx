"use client";

import { OverviewSparkline } from "@/components/overview/overview-sparkline";
import { deltaPresentation, type SummaryMetricDelta } from "@/components/ui/summary-metric";
import { formatInteger, formatPercent } from "@/lib/format";
import type { OperationOverview, OperationRegionalMatrixItem } from "@/lib/operations-api";
import { slaSystemTone } from "@/lib/operations-sla";
import { percentChange } from "@/lib/period";
import { toneTextClass, type Tone } from "@/lib/tones";
import { cn } from "@/lib/utils";

/** Séries diárias do período para o mini-gráfico de cada cartão (vazio = cartão sem sparkline). */
export type OverviewKpiSeries = {
  opened: readonly number[];
  completed: readonly number[];
  backlog: readonly number[];
  sla: readonly number[];
};

/** Atendimentos do Suporte Interno no mesmo período; `null` quando o perfil não tem acesso ao Suporte. */
export type OverviewKpiSupport = {
  total: number | null;
  closureRate: number | null;
} | null;

const EMPTY_SERIES: OverviewKpiSeries = { opened: [], completed: [], backlog: [], sla: [] };

const SPARK_COLOR: Record<"blue" | "emerald" | "amber" | "red" | "violet", string> = {
  blue: "#2563eb",
  emerald: "#0d9488",
  amber: "#d97706",
  red: "#dc3545",
  violet: "#7c72ce",
};

function pressureTone(opened: number, completed: number): Tone {
  if (!opened) return "slate";
  const ratio = completed / opened;
  if (ratio >= 1) return "emerald";
  if (ratio >= 0.9) return "amber";
  return "red";
}

/**
 * Faixa de topo (risco/aviso) no cartão inteiro - só para tons de alerta de verdade, nunca para os
 * neutros: com todos os cartões brancos, nada chamava o olho para o que estava ruim primeiro.
 */
function alertCardClass(tone: Tone): string | undefined {
  if (tone === "red") return "border-red-200 before:bg-red-500";
  if (tone === "amber") return "border-amber-200 before:bg-amber-500";
  return undefined;
}

function KpiCard({
  label,
  value,
  tone,
  hint,
  delta,
  spark,
  sparkColor,
}: {
  label: string;
  value: string;
  tone: Tone;
  hint?: string;
  delta?: SummaryMetricDelta;
  spark: readonly number[];
  sparkColor: string;
}) {
  const deltaView = delta ? deltaPresentation(delta) : null;
  const accent = alertCardClass(tone);
  return (
    <div
      className={cn(
        "relative flex min-h-[10.5rem] min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white pt-4 shadow-panel",
        accent && `${accent} before:absolute before:inset-x-0 before:top-0 before:h-[3px] before:content-['']`,
      )}
    >
      <div className="px-4">
        <p className="text-xs font-medium text-slate-600">{label}</p>
        <p className={cn("mb-2 mt-2 break-words text-[2rem] font-bold leading-tight tracking-tight tabular-nums", toneTextClass(tone))}>{value}</p>
        {deltaView ? (
          <p className={cn("flex flex-wrap items-center gap-x-1.5 text-[11px] font-semibold leading-snug", deltaView.className)}>
            <deltaView.Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span>{deltaView.text}</span>
          </p>
        ) : null}
        {hint ? <p className="mt-1 text-[11px] leading-snug text-slate-500">{hint}</p> : null}
      </div>
      <div className="mt-auto pt-2">
        <OverviewSparkline values={spark} color={sparkColor} />
      </div>
    </div>
  );
}

/**
 * Faixa de indicadores macro do período.
 *
 * Todo número aqui já vem calculado do backend - a tela só formata. O rótulo auxiliar de cada
 * cartão diz o recorte, porque "Abertas" ignora modelo de equipe/colaborador e "Em aberto" ignora
 * o período: sem isso o mesmo conjunto de cartões parece inconsistente.
 *
 * A comparação usa a janela imediatamente anterior, do mesmo tamanho (`previous`); o backlog não
 * tem comparação porque é retrato de agora, não fluxo do período.
 *
 * O quinto cartão é o Suporte Interno quando o perfil o enxerga; sem acesso, volta a ser
 * "Entrada × vazão", que não depende de permissão nenhuma.
 */
export function OverviewKpiStrip({
  overview,
  previous,
  previousLabel,
  backlog,
  canSeeSla,
  series = EMPTY_SERIES,
  support = null,
}: {
  overview: OperationOverview | null;
  /** Mesmo `overview` para a janela anterior; `null` quando não há janela comparável. */
  previous: OperationOverview | null;
  previousLabel: string;
  /**
   * Estoque em aberto vindo do quadro por filial, NÃO de `/operations/overview`.
   *
   * Divergência real encontrada na validação: o `in_progress` de `/operations/overview` aplica
   * todos os filtros ao backlog (inclusive modelo de equipe), enquanto `openings_analytics` e o
   * quadro por filial usam a convenção `_backlog_filters`, que ignora modelo de equipe e
   * responsável. Com o mesmo filtro, o card mostrava 23 e o total da tabela logo abaixo, 45. Esta
   * tela usa uma fonte só - a do quadro - para nunca se contradizer consigo mesma.
   */
  backlog: OperationRegionalMatrixItem | null;
  canSeeSla: boolean;
  series?: OverviewKpiSeries;
  support?: OverviewKpiSupport;
}) {
  const opened = overview?.opened ?? 0;
  const completed = overview?.completed ?? 0;
  const balance = opened - completed;

  const delta = (current: number | null | undefined, prev: number | null | undefined, goodWhenUp: boolean | null): SummaryMetricDelta | undefined =>
    previous ? { value: percentChange(current, prev), goodWhenUp, againstLabel: previousLabel } : undefined;

  const backlogTone: Tone = backlog?.overdue_backlog ? "amber" : "slate";
  const slaTone = slaSystemTone(overview?.sla_rate ?? null);

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
      <KpiCard
        label="Abertas no período"
        value={formatInteger(opened)}
        tone="blue"
        delta={delta(overview?.opened, previous?.opened, null)}
        hint="Demanda que entrou, qualquer equipe"
        spark={series.opened}
        sparkColor={SPARK_COLOR.blue}
      />
      <KpiCard
        label="Finalizadas"
        value={formatInteger(completed)}
        tone="emerald"
        delta={delta(overview?.completed, previous?.completed, true)}
        hint="Com os filtros aplicados"
        spark={series.completed}
        sparkColor={SPARK_COLOR.emerald}
      />
      <KpiCard
        label="Em aberto agora"
        value={formatInteger(backlog?.backlog ?? null)}
        tone={backlogTone}
        hint={
          backlog?.overdue_backlog
            ? `${formatInteger(backlog.overdue_backlog)} fora do prazo · qualquer equipe`
            : "Estoque de agora, qualquer equipe"
        }
        spark={series.backlog}
        sparkColor={SPARK_COLOR.amber}
      />
      {canSeeSla ? (
        <KpiCard
          label="SLA do período"
          value={formatPercent(overview?.sla_rate ?? null)}
          tone={slaTone}
          delta={delta(overview?.sla_rate, previous?.sla_rate, true)}
          hint="Finalizadas no prazo, com filtros"
          spark={series.sla}
          sparkColor={slaTone === "red" ? SPARK_COLOR.red : SPARK_COLOR.blue}
        />
      ) : null}
      {support ? (
        <KpiCard
          label="Atendimentos do Suporte"
          value={formatInteger(support.total)}
          tone="violet"
          hint={`Taxa de encerramento ${formatPercent(support.closureRate)}`}
          spark={[]}
          sparkColor={SPARK_COLOR.violet}
        />
      ) : (
        <KpiCard
          label="Entrada × vazão"
          value={balance > 0 ? `+${formatInteger(balance)}` : formatInteger(balance)}
          tone={pressureTone(opened, completed)}
          hint={balance > 0 ? "Entrou mais do que saiu" : "Saiu mais do que entrou"}
          spark={[]}
          sparkColor={SPARK_COLOR.violet}
        />
      )}
    </div>
  );
}
