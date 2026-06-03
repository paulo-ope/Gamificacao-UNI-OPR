"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { regionalName } from "@/lib/regional";
import type { CollaboratorScore } from "@/lib/types";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const integerFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function healthBadgeClass(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("excel")) return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (normalized.includes("boa")) return "border-blue-200 bg-blue-50 text-blue-700";
  if (normalized.includes("aten")) return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-red-200 bg-red-50 text-red-700";
}

function compactName(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 2) return name;
  return `${parts[0]} ${parts[parts.length - 1]}`;
}

function compactRegional(regional: string) {
  return regionalName(regional).replace(/^UNI\s*-\s*/i, "").replace(/\s+/g, " ").trim();
}

function formatPoints(value: number) {
  return `${numberFormat.format(value)} pts`;
}

function formatAnnulled(value: number) {
  return `${numberFormat.format(Math.abs(value))} pts anulados`;
}

function averagePointValue(score: CollaboratorScore) {
  return score.final_points > 0 ? score.estimated_payment / score.final_points : 0;
}

function MiniMetric({
  label,
  value,
  tone = "default"
}: {
  label: string;
  value: string;
  tone?: "default" | "good" | "warning" | "danger" | "money";
}) {
  const toneClass =
    tone === "good"
      ? "text-emerald-700"
      : tone === "warning"
        ? "text-amber-700"
        : tone === "danger"
          ? "text-red-600"
          : tone === "money"
            ? "text-teal-700"
            : "text-slate-950";

  return (
    <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-1.5 py-1">
      <div className="truncate text-[9px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`truncate text-xs font-semibold leading-4 ${toneClass}`}>{value}</div>
    </div>
  );
}

type RankingTableProps = {
  data: CollaboratorScore[];
  onViewOrders?: (score: CollaboratorScore) => void;
};

export function RankingTable({ data, onViewOrders }: RankingTableProps) {
  if (!data.length) {
    return (
      <div className="m-3 rounded-lg border border-dashed bg-slate-50 p-6 text-sm text-slate-500">
        Nenhum colaborador encontrado para o período atual.
      </div>
    );
  }

  return (
    <div className="grid min-w-0 gap-2 p-2">
      <div className="hidden rounded-md border bg-slate-50 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500 xl:grid xl:grid-cols-[240px_1fr_200px] xl:items-center">
        <span>Colaborador</span>
        <span>Indicadores operacionais</span>
        <span className="text-right">Resultado final</span>
      </div>

      {data.map((score, index) => (
        <article key={score.id} className="grid min-w-0 gap-3 rounded-lg border bg-white p-3 shadow-sm transition hover:border-teal-200 hover:shadow-md xl:grid-cols-[240px_1fr_200px] xl:items-center">
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <span className={index < 3 ? "flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-teal-700 text-xs font-semibold text-white" : "flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white"}>
                {index + 1}
              </span>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-slate-950" title={score.collaborator_name}>
                  {compactName(score.collaborator_name)}
                </div>
                <div className="truncate text-xs text-slate-500" title={`${score.role} - ${score.regional}`}>
                  {score.role} - {compactRegional(score.regional)}
                </div>
              </div>
            </div>
          </div>

          <div className="grid min-w-0 grid-cols-4 gap-1.5 lg:grid-cols-6 2xl:grid-cols-8">
            <MiniMetric label="Total de O.S" value={`${integerFormat.format(score.service_orders_count)} O.S`} />
            <MiniMetric label="O.S pontuadas" value={`${integerFormat.format(score.scored_service_orders ?? 0)} O.S`} tone="good" />
            <MiniMetric label="O.S sem regra" value={`${integerFormat.format(score.unscored_service_orders ?? 0)} O.S`} tone="warning" />
            <MiniMetric label="O.S anuladas" value={`${integerFormat.format(score.penalized_service_orders ?? 0)} O.S`} tone="danger" />
            <MiniMetric label="Fora prazo" value={`${integerFormat.format(score.sla_out_service_orders ?? 0)} O.S`} tone="warning" />
            <MiniMetric label="Pontos brutos" value={formatPoints(score.gross_points)} />
            <MiniMetric label="Pontos anulados" value={formatAnnulled(score.penalty_points)} tone="danger" />
            <MiniMetric label="Pontos líquidos" value={formatPoints(score.net_points)} />
          </div>

          <div className="grid min-w-0 grid-cols-[1fr_auto] items-center gap-1.5 xl:grid-cols-1 xl:text-right">
            <div className="grid min-w-0 grid-cols-2 gap-1.5 xl:grid-cols-1">
              <MiniMetric label="Pontos finais" value={formatPoints(score.final_points)} />
              <MiniMetric label="Valor a ser pago" value={moneyFormat.format(score.estimated_payment)} tone="money" />
              <div className="col-span-2 flex min-w-0 flex-wrap items-center gap-2 xl:col-span-1 xl:justify-end">
                <Badge className={healthBadgeClass(score.health_status)}>{score.health_multiplier.toFixed(2)}x</Badge>
                <span className="truncate text-xs text-slate-500">{moneyFormat.format(averagePointValue(score))}/pt medio</span>
              </div>
            </div>
            <Button variant="outline" size="sm" className="h-8 px-2" onClick={() => onViewOrders?.(score)}>
              Ver extrato
            </Button>
          </div>
        </article>
      ))}
    </div>
  );
}


