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
      {/* Colunas pela LARGURA DO CARTÃO, não da tela (`auto-fit`): o bloco divide a linha com outros dois e a
          largura dele muda com o zoom e o tamanho da janela. Com colunas fixas, o valor quebrava no meio
          ("R$ 6.07" / "8,52"). Números em `whitespace-nowrap`: nunca partem; só o texto do escopo quebra por palavra. */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(10rem,1fr))] gap-2.5">
        <SummaryMetric
          label="Valor estimado"
          value={<span className="whitespace-nowrap text-[1.15rem]">{formatMoney(data?.estimated_payment ?? null)}</span>}
          tone="violet"
          hint={data?.is_preview ? "Ainda pode mudar até o fechamento" : "Fechamento já encerrado"}
        />
        <SummaryMetric
          label="Pontos finais"
          value={<span className="whitespace-nowrap">{formatNumber(data?.final_points ?? null, 1)}</span>}
          tone="slate"
          hint={`Valor do ponto ${formatMoney(data?.point_value ?? null)}`}
        />
        <SummaryMetric
          label="Colaboradores"
          value={<span className="whitespace-nowrap">{formatInteger(data?.collaborators ?? null)}</span>}
          tone="slate"
          hint="Com pontuação no período"
        />
        <SummaryMetric
          label="Escopo"
          value={<span className="text-[1.15rem]">{data?.scope_regionals.length ? data.scope_regionals.join(", ") : "Todas as filiais"}</span>}
          tone="slate"
          hint={data?.scope_regionals.length ? "Recortado pelas suas filiais" : "Total da empresa"}
        />
      </div>
    </OverviewBlock>
  );
}
