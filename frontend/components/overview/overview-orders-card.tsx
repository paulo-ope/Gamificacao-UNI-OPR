"use client";

import { Wrench } from "lucide-react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import { OverviewProgress, OverviewTile } from "@/components/overview/overview-layout-parts";
import { deltaPresentation } from "@/components/ui/summary-metric";
import { formatInteger, formatPercent } from "@/lib/format";
import type { OperationOverview, OperationRegionalMatrixItem } from "@/lib/operations-api";
import { percentChange } from "@/lib/period";

/**
 * Ordens de serviço do período em quatro números e uma barra: abertas, concluídas, pendentes (o
 * estoque de agora, vindo do quadro por regional como no resto da tela) e entrada × vazão.
 *
 * "Garantia / retorno" do desenho original ficou de fora de propósito: o sistema não expõe essa
 * taxa por este caminho e um número inventado numa tela executiva é pior do que nenhum. No lugar
 * entra "Entrada × vazão" (abertas − concluídas), que já é calculada pelos mesmos dados.
 */
export function OverviewOrdersCard({
  overview,
  previous,
  previousLabel,
  backlog,
  state,
}: {
  overview: OperationOverview | null;
  previous: OperationOverview | null;
  previousLabel: string;
  backlog: OperationRegionalMatrixItem | null;
  state?: OverviewBlockState;
}) {
  const opened = overview?.opened ?? 0;
  const completed = overview?.completed ?? 0;
  const balance = opened - completed;

  const delta = (current: number | undefined, reference: number | undefined, goodWhenUp: boolean | null) => {
    if (!previous) return null;
    const view = deltaPresentation({ value: percentChange(current, reference), goodWhenUp, againstLabel: previousLabel });
    return { text: view.text, className: view.className };
  };
  const openedDelta = delta(overview?.opened, previous?.opened, null);
  const completedDelta = delta(overview?.completed, previous?.completed, true);

  return (
    <OverviewBlock
      eyebrow="Operação"
      title="Ordens de serviço"
      subtitle="Abertas e concluídas seguem o período e os filtros; pendentes é o estoque de agora."
      badge={<Wrench className="h-4 w-4 text-slate-400" aria-hidden="true" />}
      state={state}
    >
      <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">
        <OverviewTile
          label="Abertas"
          value={formatInteger(opened)}
          accent="blue"
          sub={openedDelta?.text ?? "sem base de comparação"}
          subClassName={openedDelta?.className}
        />
        <OverviewTile
          label="Concluídas"
          value={formatInteger(completed)}
          accent="teal"
          sub={completedDelta?.text ?? "sem base de comparação"}
          subClassName={completedDelta?.className}
        />
        <OverviewTile
          label="Pendentes · atual"
          value={formatInteger(backlog?.backlog ?? null)}
          accent="amber"
          sub={backlog?.overdue_backlog ? `${formatInteger(backlog.overdue_backlog)} fora do prazo` : "estoque de agora"}
        />
        <OverviewTile
          label="Entrada × vazão"
          value={balance > 0 ? `+${formatInteger(balance)}` : formatInteger(balance)}
          accent="violet"
          sub={balance > 0 ? "entrou mais do que saiu" : "saiu mais do que entrou"}
        />
      </div>
      <OverviewProgress
        leftLabel="Finalizadas"
        leftValue={opened > 0 ? formatPercent((completed / opened) * 100) : "—"}
        rightLabel="Pendentes"
        rightValue={formatInteger(backlog?.backlog ?? null)}
        percent={opened > 0 ? (completed / opened) * 100 : null}
      />
    </OverviewBlock>
  );
}
