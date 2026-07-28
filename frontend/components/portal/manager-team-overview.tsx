"use client";

import { AlertTriangle, Activity, ArrowDownRight, ArrowUpRight, Gauge, Medal, ShieldCheck, Target, UsersRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { PortalTeamSummary } from "@/lib/types";

type Props = {
  team: PortalTeamSummary;
};

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function number(value: number | null | undefined) {
  return numberFormat.format(Number(value ?? 0));
}

function money(value: number | null | undefined) {
  return moneyFormat.format(Number(value ?? 0));
}

function period(month: number | null | undefined, year: number | null | undefined) {
  if (!month || !year) return "--";
  return `${String(month).padStart(2, "0")}/${year}`;
}

function bandClass(label: string | null | undefined) {
  if (label === "Acima da faixa") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (label === "Abaixo da faixa") return "border-rose-200 bg-rose-50 text-rose-800";
  return "border-[#2d5fff]/25 bg-[#2d5fff]/10 text-[#0028f3]";
}

function MiniMetric({
  label,
  value,
  hint,
  icon: Icon,
  tone = "neutral"
}: {
  label: string;
  value: string;
  hint: string;
  icon: typeof Gauge;
  tone?: "neutral" | "good" | "warn";
}) {
  const toneClass =
    tone === "good"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : tone === "warn"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : "border-[#2d5fff]/20 bg-white text-slate-950";
  return (
    <div className={`min-w-0 rounded-lg border p-4 shadow-sm ${toneClass}`}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
        <Icon className="h-4 w-4 shrink-0" />
      </div>
      <p className="mt-3 break-words text-2xl font-semibold leading-tight">{value}</p>
      <p className="mt-1 text-sm text-slate-600">{hint}</p>
    </div>
  );
}

export function ManagerTeamOverview({ team }: Props) {
  const totals = team.totals;
  const history = team.history ?? [];
  const last = history.at(-1);
  const previous = history.length > 1 ? history.at(-2) : null;
  const slaDelta = last && previous ? Number(last.sla_rate) - Number(previous.sla_rate) : 0;
  const maxHistoryPoints = Math.max(1, ...history.map((item) => item.final_points));
  const maxBand = Math.max(1, ...(team.bands ?? []).map((item) => item.collaborators));
  const averagePoints = totals?.collaborators ? Number(totals.final_points) / Math.max(1, totals.collaborators) : 0;

  if (!totals) {
    return (
      <section className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
        {team.message ?? "Nenhum dado de equipe disponível para este acesso."}
      </section>
    );
  }

  return (
    <section className="space-y-5">
      <section className="overflow-hidden rounded-lg border bg-white shadow-sm">
        <div className="uni-gradient p-5 text-white sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-sm font-medium text-[#02fffa]">UNI OPR · Gestão regional</p>
              <h2 className="mt-1 break-words text-2xl font-semibold leading-tight sm:text-3xl">{team.regional ?? "Minha regional"}</h2>
              <p className="mt-2 max-w-2xl text-sm text-white/80">
                Leitura do time no fechamento {period(team.period.reference_month, team.period.reference_year)}.
              </p>
            </div>
            <div className="grid w-full grid-cols-2 gap-2 sm:w-auto">
              <div className="rounded-lg border border-white/25 bg-white/15 px-3 py-2">
                <p className="text-xs text-white/70">SLA regional</p>
                <p className="mt-1 text-xl font-semibold text-[#02fffa]">{number(totals.sla_rate)}%</p>
              </div>
              <div className="rounded-lg border border-white/25 bg-white/15 px-3 py-2">
                <p className="text-xs text-white/70">Saúde média</p>
                <p className="mt-1 text-xl font-semibold text-[#02fffa]">{number(totals.health_average)}x</p>
              </div>
            </div>
          </div>
        </div>
        {team.alerts?.length ? (
          <div className="grid gap-2 border-t border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            {team.alerts.map((alert) => (
              <div key={alert} className="flex gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{alert}</span>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MiniMetric icon={UsersRound} label="Colaboradores" value={number(totals.collaborators)} hint={`${number(totals.service_orders)} O.S. no período`} />
        <MiniMetric icon={Target} label="Pontuação" value={`${number(totals.final_points)} pts`} hint={`Média de ${number(averagePoints)} pts por colaborador`} />
        <MiniMetric icon={ShieldCheck} label="SLA no prazo" value={`${number(totals.sla_rate)}%`} hint={`${number(totals.sla_out_service_orders)} O.S. fora do SLA`} tone={totals.sla_rate >= 90 ? "good" : "warn"} />
        <MiniMetric icon={Gauge} label="Pagamento" value={money(totals.estimated_payment)} hint={`${number(totals.penalty_points)} pts em descontos`} />
      </section>

      <section className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-lg border bg-white p-4 shadow-sm sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h3 className="font-semibold">Tendência de SLA e pontuação</h3>
              <p className="mt-1 text-sm text-slate-500">Acompanhe a evolução recente da regional.</p>
            </div>
            <Badge className={slaDelta >= 0 ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}>
              {slaDelta >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
              {slaDelta >= 0 ? "+" : ""}{number(slaDelta)} p.p.
            </Badge>
          </div>
          <div className="mt-5 space-y-4">
            {history.map((item) => (
              <div key={`${item.reference_month}-${item.reference_year}`}>
                <div className="mb-1 grid gap-1 text-sm sm:grid-cols-[88px_1fr_auto] sm:items-center sm:gap-3">
                  <p className="font-medium">{period(item.reference_month, item.reference_year)}</p>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-[#2d5fff]" style={{ width: `${Math.max(4, (item.final_points / maxHistoryPoints) * 100)}%` }} />
                  </div>
                  <p className="text-sm font-semibold text-slate-900">{number(item.sla_rate)}% SLA</p>
                </div>
                <p className="text-xs text-slate-500">
                  {number(item.final_points)} pts · {number(item.service_orders)} O.S. · {number(item.recurrence_rate)}% reincidência
                </p>
              </div>
            ))}
            {!history.length ? <p className="text-sm text-slate-500">Ainda não há histórico suficiente para tendência.</p> : null}
          </div>
        </div>

        <div className="rounded-lg border bg-white p-4 shadow-sm sm:p-5">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-[#0028f3]" />
            <h3 className="font-semibold">Faixas do time</h3>
          </div>
          <div className="mt-5 space-y-4">
            {(team.bands ?? []).filter((band) => band.collaborators > 0).map((band) => (
              <div key={band.label}>
                <div className="flex items-center justify-between gap-3 text-sm">
                  <div className="min-w-0">
                    <p className="font-medium">{band.label}</p>
                    <p className="text-xs text-slate-500">{band.description}</p>
                  </div>
                  <Badge className={bandClass(band.label)}>{band.collaborators}</Badge>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-slate-900" style={{ width: `${Math.max(5, (band.collaborators / maxBand) * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 shadow-sm sm:p-5">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-800" />
            <h3 className="font-semibold text-amber-950">Acompanhamento prioritário</h3>
          </div>
          <div className="mt-4 space-y-3">
            {(team.attention ?? []).slice(0, 6).map((item) => (
              <div key={item.collaborator_id} className="rounded-lg border border-amber-200 bg-white p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{item.collaborator_name}</p>
                    <p className="mt-1 text-xs text-amber-900">{item.attention_reason}</p>
                  </div>
                  <Badge className={bandClass(item.performance_band)}>{item.performance_band}</Badge>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-slate-600">
                  <span><b className="text-slate-950">{number(item.final_points)}</b><br />pts</span>
                  <span><b className="text-slate-950">{item.sla_out_service_orders}</b><br />SLA fora</span>
                  <span><b className="text-slate-950">{number(item.target_gap)}</b><br />até média</span>
                </div>
              </div>
            ))}
            {!team.attention?.length ? <p className="text-sm text-emerald-900">Nenhum colaborador em atenção crítica neste fechamento.</p> : null}
          </div>
        </div>

        <div className="overflow-hidden rounded-lg border bg-white shadow-sm">
          <div className="border-b px-4 py-3">
            <h3 className="font-semibold">Ranking acionável do time</h3>
          </div>
          <div className="divide-y">
            {team.ranking.map((item) => (
              <div key={item.collaborator_id} className="grid gap-3 px-4 py-3 sm:grid-cols-[auto_1fr_auto] sm:items-center">
                <span className="text-sm font-semibold text-slate-500">#{item.position}</span>
                <div className="min-w-0">
                  <p className="truncate font-medium">{item.collaborator_name}</p>
                  <p className="truncate text-xs text-slate-500">
                    {item.service_orders_count} O.S. · {item.scored_service_orders} pontuadas · {item.health_multiplier.toFixed(2)}x saúde
                  </p>
                </div>
                <div className="sm:text-right">
                  <p className="font-semibold">{number(item.final_points)} pts</p>
                  <Badge className={bandClass(item.performance_band)}>{item.performance_band}</Badge>
                </div>
              </div>
            ))}
            {!team.ranking.length ? <p className="px-4 py-4 text-sm text-slate-500">Nenhum colaborador pontuado nesta regional ainda.</p> : null}
          </div>
        </div>
      </section>
    </section>
  );
}
