"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { OverviewBlock, type OverviewBlockState } from "@/components/overview/overview-block";
import { SummaryMetric } from "@/components/ui/summary-metric";
import { formatDateTime, formatInteger, formatMoney, formatNumber } from "@/lib/format";
import type { GamificationPreview } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  draft: "Prévia (rascunho)",
  review: "Em revisão",
  approved: "Aprovado",
  paid: "Pago",
  cancelled: "Cancelado",
};

/**
 * Valor corrente da gamificação.
 *
 * É a prévia do mês em curso, que o recálculo automático do IXC regrava a cada ciclo - não o
 * último fechamento pago. Por isso o cartão sempre mostra quando o número foi calculado e em que
 * status ele está: um mês já pago congela o valor, e uma sincronização parada deixa a prévia
 * velha. Mostrar o número sem essa data já foi fonte de confusão em telas de fechamento.
 */
export function OverviewGamificationCard({
  data,
  state,
}: {
  data: GamificationPreview | null;
  state?: OverviewBlockState;
}) {
  const referenceLabel = data
    ? `${String(data.reference_month).padStart(2, "0")}/${data.reference_year}`
    : "—";
  const statusLabel = data?.status ? (STATUS_LABEL[data.status] ?? data.status) : null;

  return (
    <OverviewBlock
      eyebrow="Gamificação Operacional"
      title={`Prévia de ${referenceLabel}`}
      subtitle={
        data?.available
          ? `Calculada em ${formatDateTime(data.calculated_at)}`
          : "Prévia do mês corrente, recalculada junto com a sincronização do IXC."
      }
      badge={statusLabel ?? undefined}
      actions={
        <Link
          href="/gamificacao"
          className="inline-flex items-center gap-1 text-[11px] font-semibold text-uni-royal hover:underline"
        >
          Abrir módulo
          <ArrowUpRight className="h-3 w-3" />
        </Link>
      }
      state={{ ...state, empty: !state?.loading && !state?.error && data !== null && !data.available }}
      emptyLabel={data?.unavailable_reason ?? "Prévia indisponível para o mês corrente."}
      deniedLabel="Seu perfil não tem acesso aos valores da gamificação."
    >
      <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">
        <SummaryMetric
          label="Valor estimado"
          value={formatMoney(data?.estimated_payment ?? null)}
          tone="violet"
          hint={data?.is_preview ? "Ainda pode mudar até o fechamento" : "Fechamento já encerrado"}
        />
        <SummaryMetric
          label="Pontos finais"
          value={formatNumber(data?.final_points ?? null, 1)}
          tone="slate"
          hint={`Valor do ponto ${formatMoney(data?.point_value ?? null)}`}
        />
        <SummaryMetric
          label="Colaboradores"
          value={formatInteger(data?.collaborators ?? null)}
          tone="slate"
          hint="Com pontuação no período"
        />
        <SummaryMetric
          label="Escopo"
          value={data?.scope_regionals.length ? data.scope_regionals.join(", ") : "Todas as filiais"}
          tone="slate"
          hint={data?.scope_regionals.length ? "Recortado pelas suas filiais" : "Total da empresa"}
        />
      </div>
    </OverviewBlock>
  );
}
