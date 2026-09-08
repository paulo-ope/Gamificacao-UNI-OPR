"use client";

import { CheckCircle2, Gauge, Inbox, ListChecks, Scale } from "lucide-react";

import { SummaryMetric, type SummaryMetricDelta } from "@/components/ui/summary-metric";
import { formatInteger, formatPercent } from "@/lib/format";
import type { OperationOverview, OperationRegionalMatrixItem } from "@/lib/operations-api";
import { slaSystemTone } from "@/lib/operations-sla";
import { percentChange } from "@/lib/period";
import type { Tone } from "@/lib/tones";

function pressureTone(opened: number, completed: number): Tone {
  if (!opened) return "slate";
  const ratio = completed / opened;
  if (ratio >= 1) return "emerald";
  if (ratio >= 0.9) return "amber";
  return "red";
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
 */
export function OverviewKpiStrip({
  overview,
  previous,
  previousLabel,
  backlog,
  canSeeSla,
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
}) {
  const opened = overview?.opened ?? 0;
  const completed = overview?.completed ?? 0;
  const balance = opened - completed;

  const delta = (current: number | null | undefined, prev: number | null | undefined, goodWhenUp: boolean | null): SummaryMetricDelta | undefined =>
    previous ? { value: percentChange(current, prev), goodWhenUp, againstLabel: previousLabel } : undefined;

  return (
    <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 xl:grid-cols-5">
      <SummaryMetric
        label="Abertas no período"
        value={formatInteger(opened)}
        icon={Inbox}
        tone="blue"
        delta={delta(overview?.opened, previous?.opened, null)}
        hint="Demanda que entrou, qualquer equipe"
      />
      <SummaryMetric
        label="Finalizadas"
        value={formatInteger(completed)}
        icon={CheckCircle2}
        tone="emerald"
        delta={delta(overview?.completed, previous?.completed, true)}
        hint="Com os filtros aplicados"
      />
      <SummaryMetric
        label="Entrada × vazão"
        value={balance > 0 ? `+${formatInteger(balance)}` : formatInteger(balance)}
        icon={Scale}
        tone={pressureTone(opened, completed)}
        hint={balance > 0 ? "Entrou mais do que saiu" : "Saiu mais do que entrou"}
      />
      <SummaryMetric
        label="Em aberto agora"
        value={formatInteger(backlog?.backlog ?? null)}
        icon={ListChecks}
        tone={backlog?.overdue_backlog ? "amber" : "slate"}
        hint={
          backlog?.overdue_backlog
            ? `${formatInteger(backlog.overdue_backlog)} fora do prazo · qualquer equipe`
            : "Estoque de agora, qualquer equipe"
        }
      />
      {canSeeSla ? (
        <SummaryMetric
          label="SLA do período"
          value={formatPercent(overview?.sla_rate ?? null)}
          icon={Gauge}
          tone={slaSystemTone(overview?.sla_rate ?? null)}
          delta={delta(overview?.sla_rate, previous?.sla_rate, true)}
          hint="Finalizadas no prazo, com filtros"
        />
      ) : null}
    </div>
  );
}
