"use client";

import { Medal, ShieldAlert, Target, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScoreTransparencyPanel } from "@/components/portal/score-transparency-panel";
import type { PortalAudit, PortalSummary } from "@/lib/types";

type Props = {
  audit: PortalAudit;
  summary: PortalSummary;
  onOpenOrders: () => void;
};

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function points(value: number | null | undefined) {
  return `${numberFormat.format(Number(value ?? 0))} pts`;
}

function money(value: number | null | undefined) {
  return moneyFormat.format(Number(value ?? 0));
}

export function CollaboratorOverview({ audit, summary, onOpenOrders }: Props) {
  const collaborator = summary.collaborator;
  const rankingLabel = summary.regional_position ? `${summary.regional_position}º` : "--";
  const hasAction = audit.unscored_service_orders + audit.manual_review_service_orders + audit.sla_out_service_orders > 0;
  const topGroups = audit.groups.slice(0, 4);
  const maxPoints = Math.max(1, ...topGroups.map((item) => item.net_points));
  const healthPoints = audit.final_points - audit.net_points - audit.balance_adjustment_points;
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

      <section className="hidden gap-3 md:grid lg:grid-cols-[1.1fr_0.9fr]">
        <div className="overflow-hidden rounded-lg border bg-white">
          <div className="p-5">
          <div className="flex items-center gap-2"><Target className="h-4 w-4 text-[#0028f3]" /><h3 className="font-semibold">A viagem dos seus pontos</h3></div>
          <p className="mt-1 text-sm text-slate-500">A conta do fechamento, com cada ajuste separado.</p>
          </div>
          <div className="grid divide-y border-y sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4">
            <div className="p-4"><p className="text-xs font-medium uppercase text-slate-500">Pontos nas O.S.</p><p className="mt-2 text-2xl font-semibold">{points(audit.gross_points)}</p><p className="mt-1 text-xs text-slate-500">Antes das regras.</p></div>
            <div className="bg-amber-50/70 p-4"><p className="text-xs font-medium uppercase text-amber-800">Regras aplicadas</p><p className="mt-2 text-2xl font-semibold text-amber-950">-{points(audit.penalty_points)}</p><p className="mt-1 text-xs text-amber-900">Recorrência, garantia, SLA ou diagnóstico.</p></div>
            <div className="bg-[#27d9bf]/10 p-4"><p className="text-xs font-medium uppercase text-[#006d61]">Saúde operacional</p><p className="mt-2 text-2xl font-semibold text-[#006d61]">{healthPoints >= 0 ? "+" : ""}{points(healthPoints)}</p><p className="mt-1 text-xs text-[#006d61]">Ajuste de desempenho regional.</p></div>
            <div className="p-4"><p className="text-xs font-medium uppercase text-slate-500">Saldo de garantia</p><p className="mt-2 text-2xl font-semibold">{audit.balance_adjustment_points >= 0 ? "+" : ""}{points(audit.balance_adjustment_points)}</p><p className="mt-1 text-xs text-slate-500">Créditos ou débitos deste período.</p></div>
          </div>
          <div className="uni-gradient-soft flex flex-wrap items-center justify-between gap-2 px-5 py-4"><p className="text-sm font-medium text-slate-700">{points(audit.gross_points)} - {points(audit.penalty_points)} {healthPoints >= 0 ? "+" : "-"} {points(Math.abs(healthPoints))} {audit.balance_adjustment_points >= 0 ? "+" : "-"} {points(Math.abs(audit.balance_adjustment_points))}</p><p className="text-lg font-semibold text-[#0028f3]">Resultado final: {points(audit.final_points)}</p></div>
        </div>
        <div className={`rounded-lg border p-5 ${hasAction ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}>
          <div className="flex items-center gap-2"><ShieldAlert className={`h-4 w-4 ${hasAction ? "text-amber-800" : "text-emerald-700"}`} /><h3 className="font-semibold">Seu foco agora</h3></div>
          {hasAction ? <div className="mt-4 space-y-3 text-sm text-slate-700"><p>Estes itens merecem atenção. Eles não são uma punição: mostram O.S. que podem precisar de conferência ou que tiveram uma regra aplicada.</p><div className="grid grid-cols-3 gap-2"><div><p className="text-xl font-semibold">{audit.unscored_service_orders}</p><p className="text-xs">sem regra</p></div><div><p className="text-xl font-semibold">{audit.manual_review_service_orders}</p><p className="text-xs">em revisão</p></div><div><p className="text-xl font-semibold">{audit.sla_out_service_orders}</p><p className="text-xs">SLA fora</p></div></div></div> : <p className="mt-4 text-sm text-emerald-900">Não há pendências de regra, revisão ou SLA destacadas neste fechamento.</p>}
        </div>
      </section>

      <section className="hidden gap-5 md:grid lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-lg border bg-white p-5">
          <div className="flex items-center gap-2"><TrendingUp className="h-4 w-4 text-[#0028f3]" /><h3 className="font-semibold">Onde você mais pontuou</h3></div>
          <div className="mt-5 space-y-4">
            {topGroups.map((group) => <div key={group.label}><div className="grid gap-1 text-sm sm:grid-cols-[1fr_auto] sm:items-center sm:gap-3"><div className="min-w-0"><p className="truncate font-medium">{group.label}</p><p className="text-xs text-slate-500">{group.service_orders} O.S.</p></div><p className="font-semibold sm:whitespace-nowrap">{points(group.net_points)}</p></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#2d5fff]" style={{ width: `${Math.max(4, (group.net_points / maxPoints) * 100)}%` }} /></div></div>)}
            {!topGroups.length ? <p className="text-sm text-slate-500">Ainda não há O.S. pontuadas para agrupar.</p> : null}
          </div>
        </div>
        <div className="rounded-lg border bg-white p-5">
          <div className="flex items-center gap-2"><Medal className="h-4 w-4 text-[#0028f3]" /><h3 className="font-semibold">Sua evolução</h3></div>
          <div className="mt-5 space-y-3">
            {audit.history.slice(-4).reverse().map((item) => <div key={`${item.reference_month}-${item.reference_year}`} className="grid gap-2 border-b border-slate-100 pb-3 last:border-0 sm:grid-cols-[1fr_auto] sm:items-center sm:gap-3"><div><p className="font-medium">{String(item.reference_month).padStart(2, "0")}/{item.reference_year}</p><p className="text-xs text-slate-500">{item.service_orders_count} O.S. no fechamento</p></div><div className="sm:text-right"><p className="font-semibold">{points(item.final_points)}</p><p className="text-xs text-slate-500">{money(item.estimated_payment)}</p></div></div>)}
            {!audit.history.length ? <p className="text-sm text-slate-500">Seu histórico aparecerá a partir dos próximos fechamentos.</p> : null}
          </div>
        </div>
      </section>
    </section>
  );
}
