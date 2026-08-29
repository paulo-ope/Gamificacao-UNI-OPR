"use client";

import { ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ScoreTransparencyPanel } from "@/components/portal/score-transparency-panel";
import type { PortalAudit, PortalSummary } from "@/lib/types";

type Props = {
  audit: PortalAudit;
  summary: PortalSummary;
  onOpenOrders: () => void;
};

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

function points(value: number | null | undefined) {
  return `${numberFormat.format(Number(value ?? 0))} pts`;
}

export function CollaboratorOverview({ audit, summary, onOpenOrders }: Props) {
  const collaborator = summary.collaborator;
  const rankingLabel = summary.regional_position ? `${summary.regional_position}º` : "--";
  const hasAction = audit.unscored_service_orders + audit.manual_review_service_orders + audit.sla_out_service_orders > 0;
  const regionalAverage = summary.ranking.length
    ? summary.ranking.reduce((total, item) => total + item.final_points, 0) / summary.ranking.length
    : 0;
  const pointsVsAverage = audit.final_points - regionalAverage;
  const healthMultiplierEffect = audit.net_points * (audit.health_multiplier - 1);
  const regionalSlaOnTimeOrders = Math.max(0, summary.regional_service_orders - summary.regional_sla_out_service_orders);

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm text-slate-500">{collaborator?.regional ?? "Regional não vinculada"}</p>
          <h2 className="mt-1 break-words text-xl font-semibold leading-tight sm:text-2xl">Olá, {collaborator?.name?.split(" ")[0] ?? summary.user.name.split(" ")[0]}</h2>
          <p className="mt-1 text-sm text-slate-600">Aqui está sua leitura do fechamento atual, sem mistério.</p>
        </div>
        <Badge className="border-[#2d5fff]/25 bg-[#2d5fff]/10 px-3 py-1 text-[#0028f3]">Atualizado no fechamento</Badge>
      </div>

      <ScoreTransparencyPanel audit={audit} summary={summary} onOpenOrders={onOpenOrders} />

      <section className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <p className="text-xs font-medium uppercase text-slate-500">Na regional</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">{rankingLabel}</p>
          <p className="mt-1 text-sm text-slate-500">de {summary.regional_total} colaboradores</p>
        </div>
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <p className="text-xs font-medium uppercase text-slate-500">Média regional</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">{points(regionalAverage)}</p>
          <p className="mt-1 text-sm text-slate-500">referência do seu grupo</p>
        </div>
        <div className={`rounded-lg border p-4 shadow-sm ${pointsVsAverage >= 0 ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
          <p className={`text-xs font-medium uppercase ${pointsVsAverage >= 0 ? "text-emerald-700" : "text-amber-800"}`}>Comparação</p>
          <p className={`mt-2 text-2xl font-semibold ${pointsVsAverage >= 0 ? "text-emerald-800" : "text-amber-950"}`}>
            {pointsVsAverage >= 0 ? "+" : "-"}{points(Math.abs(pointsVsAverage))}
          </p>
          <p className={`mt-1 text-sm ${pointsVsAverage >= 0 ? "text-emerald-700" : "text-amber-900"}`}>
            {pointsVsAverage >= 0 ? "acima da média regional" : "abaixo da média regional"}
          </p>
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg border bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase text-slate-500">SLA da regional</p>
              <p className="mt-2 text-3xl font-semibold text-slate-950">
                {summary.regional_sla_rate === null ? "Sem medição" : `${numberFormat.format(summary.regional_sla_rate)}%`}
              </p>
            </div>
            <Badge className={summary.regional_sla_rate !== null && summary.regional_sla_rate < 90 ? "border-amber-200 bg-amber-50 text-amber-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}>
              {regionalSlaOnTimeOrders} no prazo
            </Badge>
          </div>
          <p className="mt-3 text-sm text-slate-600">
            {summary.regional_service_orders
              ? `${regionalSlaOnTimeOrders} de ${summary.regional_service_orders} O.S. de colaboradores cadastrados ficaram no prazo.`
              : "Ainda não há O.S. de colaboradores cadastrados na regional para calcular este indicador."}
          </p>
          {summary.regional_sla_out_service_orders ? <p className="mt-2 text-xs text-slate-500">{summary.regional_sla_out_service_orders} O.S. de colaboradores cadastrados ficaram fora do prazo.</p> : null}
        </div>
        <div className="rounded-lg border bg-white p-5 shadow-sm">
          <p className="text-xs font-medium uppercase text-slate-500">Saúde operacional</p>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <p className="text-3xl font-semibold text-slate-950">{numberFormat.format(audit.health_multiplier)}x</p>
            <p className={`text-sm font-medium ${healthMultiplierEffect >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
              {healthMultiplierEffect >= 0 ? "+" : ""}{points(healthMultiplierEffect)} no resultado
            </p>
          </div>
          <p className="mt-3 text-sm text-slate-600">{audit.health_status}. Este multiplicador é aplicado sobre seus pontos líquidos antes do saldo de garantia.</p>
        </div>
      </section>

      {/* "A viagem dos seus pontos", "Onde você mais pontuou" e "Sua evolução" saíram daqui: eram
          os mesmos audit.gross_points/penalty_points/groups/history já mostrados em
          ScoreTransparencyPanel ("Composição do cálculo", "Onde seus pontos nasceram", "Evolução
          dos fechamentos"), duas vezes na mesma tela (crítica de design de 2026-08-28). "Seu foco
          agora" é o único conteúdo desta seção sem equivalente lá em cima - fica sozinho. */}
      <section className={`hidden rounded-lg border p-5 md:block ${hasAction ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}>
        <div className="flex items-center gap-2"><ShieldAlert className={`h-4 w-4 ${hasAction ? "text-amber-800" : "text-emerald-700"}`} /><h3 className="font-semibold">Seu foco agora</h3></div>
        {hasAction ? <div className="mt-4 space-y-3 text-sm text-slate-700"><p>Estes itens merecem atenção. Eles não são uma punição: mostram O.S. que podem precisar de conferência ou que tiveram uma regra aplicada.</p><div className="grid grid-cols-3 gap-2"><div><p className="text-xl font-semibold">{audit.unscored_service_orders}</p><p className="text-xs">sem regra</p></div><div><p className="text-xl font-semibold">{audit.manual_review_service_orders}</p><p className="text-xs">em revisão</p></div><div><p className="text-xl font-semibold">{audit.sla_out_service_orders}</p><p className="text-xs">SLA fora</p></div></div></div> : <p className="mt-4 text-sm text-emerald-900">Não há pendências de regra, revisão ou SLA destacadas neste fechamento.</p>}
      </section>
    </section>
  );
}
