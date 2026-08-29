"use client";

import { BarChart3, Gauge, ListTree, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { PortalAudit, PortalSummary } from "@/lib/types";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function formatPoints(value: number | null | undefined) {
  return `${numberFormat.format(Number(value ?? 0))} pts`;
}

function formatMultiplier(value: number | null | undefined) {
  const numeric = Number(value ?? 0);
  return `${numeric >= 0 ? "+" : ""}${numberFormat.format(numeric)}x`;
}

function formatCpk(value: number | null | undefined) {
  if (value == null) return "Não informado";
  return numberFormat.format(value);
}

function cpkBadgeClass(status: string | null | undefined) {
  if (status === "na_meta") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (status === "fora_meta") return "border-rose-200 bg-rose-50 text-rose-700";
  if (status === "sem_base") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

function stepBarClass(kind: string, value: number) {
  if (kind === "negative" || value < 0) return "bg-rose-500";
  if (kind === "total") return "bg-[#0028f3]";
  if (kind === "subtotal") return "bg-cyan-600";
  return "bg-emerald-500";
}

// Única representação de "Composição do cálculo", em todas as larguras de tela - antes coexistia
// com um gráfico de barras ECharts que mostrava os MESMOS 6 números (achado da crítica de design
// de 2026-08-28: mesma pontuação repetida em dois componentes visuais na mesma tela). O gráfico
// também exigia rótulos do eixo X rotacionados pra caber 6 categorias, o que prejudicava a leitura
// - a barra com rótulo ao lado não tem esse problema.
function StepBars({ steps }: { steps: Array<{ key: string; label: string; value: number; kind: string; description?: string | null }> }) {
  const maxValue = Math.max(1, ...steps.map((step) => Math.abs(Number(step.value || 0))));

  return (
    <div className="mt-4 space-y-3">
      {steps.map((step) => {
        const width = Math.max(8, Math.min(100, (Math.abs(step.value) / maxValue) * 100));
        return (
          <div key={step.key} className="rounded-2xl border bg-white p-3 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-950">{step.label}</p>
                {step.description ? <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{step.description}</p> : null}
              </div>
              <p className={`shrink-0 text-sm font-bold ${step.value < 0 ? "text-rose-700" : "text-slate-950"}`}>{formatPoints(step.value)}</p>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
              <div className={`h-full rounded-full ${stepBarClass(step.kind, step.value)}`} style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Substitui o donut ECharts "Onde seus pontos nasceram". Um donut com furo de 48%-72% de raio,
// quando uma categoria domina quase tudo (ex: 97% num único grupo), vira majoritariamente um anel
// fino de uma cor só cercado de espaço em branco - lê como "gráfico vazio", não como dado. Uma
// barra com o percentual explícito comunica a mesma distribuição sem essa ambiguidade visual.
function GroupBars({ groups }: { groups: PortalAudit["groups"] }) {
  const maxValue = Math.max(1, ...groups.map((group) => Math.max(0, group.net_points)));

  return (
    <div className="mt-4 space-y-3">
      {groups.map((group) => {
        const width = Math.max(6, Math.min(100, (Math.max(0, group.net_points) / maxValue) * 100));
        return (
          <div key={group.label} className="rounded-2xl border bg-white p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-950">{group.label}</p>
                <p className="text-xs text-slate-500">{group.service_orders} O.S. · base {formatPoints(group.base_points)}</p>
              </div>
              <p className="shrink-0 text-sm font-bold text-[#0028f3]">{formatPoints(group.net_points)}</p>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-gradient-to-r from-[#2d5fff] to-[#27d9bf]" style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function HistoryList({ history }: { history: PortalAudit["history"] }) {
  const recentHistory = history.slice(-4).reverse();

  return (
    <div className="mt-4 space-y-2">
      {recentHistory.map((item) => (
        <div key={`${item.reference_month}-${item.reference_year}`} className="flex items-center justify-between gap-3 rounded-2xl border bg-white p-3">
          <div>
            <p className="text-sm font-semibold text-slate-950">{String(item.reference_month).padStart(2, "0")}/{item.reference_year}</p>
            <p className="text-xs text-slate-500">{item.service_orders_count} O.S. · {moneyFormat.format(item.estimated_payment)}</p>
          </div>
          <p className="text-sm font-bold text-[#0028f3]">{formatPoints(item.final_points)}</p>
        </div>
      ))}
    </div>
  );
}

type Props = {
  audit: PortalAudit;
  summary: PortalSummary;
  onOpenOrders: () => void;
};

export function ScoreTransparencyPanel({ audit, summary, onOpenOrders }: Props) {
  const scoreSteps = audit.score_steps?.length
    ? audit.score_steps
    : [
        { key: "gross_points", label: "Pontos das O.S.", value: audit.gross_points, kind: "positive", description: "Soma dos pontos configurados para as O.S. do período." },
        { key: "penalty_points", label: "Regras e anulações", value: -Math.abs(audit.penalty_points), kind: audit.penalty_points ? "negative" : "neutral", description: "Descontos aplicados pelas regras." },
        { key: "net_points", label: "Pontos líquidos", value: audit.net_points, kind: "subtotal", description: "Resultado antes da saúde operacional." },
        { key: "health_multiplier", label: `Saúde operacional (${audit.health_multiplier.toFixed(2)}x)`, value: audit.net_points * audit.health_multiplier - audit.net_points, kind: "neutral", description: "Impacto do multiplicador da regional." },
        { key: "balance_adjustment_points", label: "Saldo de garantia", value: audit.balance_adjustment_points, kind: "neutral", description: "Créditos ou débitos de garantia." },
        { key: "final_points", label: "Resultado final", value: audit.final_points, kind: "total", description: "Pontuação final do ranking." }
      ];
  const visibleScoreSteps = scoreSteps.filter((step) => step.key !== "cpk");
  const groupData = audit.groups.slice(0, 7);

  return (
    <section className="space-y-4">
      <section className="overflow-hidden rounded-[1.75rem] border bg-white shadow-sm">
        <div className="uni-gradient p-4 text-white sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/70">Extrato da pontuação</p>
              <h3 className="mt-2 text-xl font-semibold leading-tight sm:text-2xl">Seu cálculo, aberto e fácil de conferir</h3>
              <p className="mt-2 max-w-3xl text-sm text-white/80">
                O.S., regras, saúde operacional, CPK e saldo de garantia em uma leitura única.
              </p>
            </div>
            <Button className="h-11 w-full border-white/35 bg-white/10 text-white hover:bg-white/20 sm:w-auto" variant="outline" onClick={onOpenOrders}>
              <ListTree className="h-4 w-4" />
              Auditar O.S.
            </Button>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-4">
            <div className="rounded-2xl border border-white/20 bg-white/10 p-3 sm:p-4">
              <p className="text-xs text-white/70">Resultado final</p>
              <p className="mt-1 text-xl font-semibold leading-tight sm:text-2xl">{formatPoints(audit.final_points)}</p>
              <p className="mt-1 text-xs text-white/70">{moneyFormat.format(audit.estimated_payment)} estimado</p>
            </div>
            <div className="rounded-2xl border border-white/20 bg-white/10 p-3 sm:p-4">
              <p className="text-xs text-white/70">Pontos líquidos</p>
              <p className="mt-1 text-xl font-semibold leading-tight sm:text-2xl">{formatPoints(audit.net_points)}</p>
              <p className="mt-1 text-xs text-white/70">{audit.scored_service_orders} O.S. pontuadas</p>
            </div>
            <div className="rounded-2xl border border-white/20 bg-white/10 p-3 sm:p-4">
              <p className="text-xs text-white/70">Saúde operacional</p>
              <p className="mt-1 text-xl font-semibold leading-tight sm:text-2xl">{numberFormat.format(audit.health_multiplier)}x</p>
              <p className="mt-1 text-xs text-white/70">{audit.health_status}</p>
            </div>
            <div className="rounded-2xl border border-white/20 bg-white/10 p-3 sm:p-4">
              <p className="text-xs text-white/70">Posição regional</p>
              <p className="mt-1 text-xl font-semibold leading-tight sm:text-2xl">{summary.regional_position ? `${summary.regional_position}º` : "--"}</p>
              <p className="mt-1 text-xs text-white/70">de {summary.regional_total} colaboradores</p>
            </div>
          </div>
        </div>
        <div className="grid divide-y lg:grid-cols-[1.35fr_0.65fr] lg:divide-x lg:divide-y-0">
          <div className="p-3 sm:p-5">
            <div className="flex items-center gap-2 px-1">
              <BarChart3 className="h-4 w-4 text-[#0028f3]" />
              <h4 className="font-semibold text-slate-950">Composição do cálculo</h4>
            </div>
            <StepBars steps={visibleScoreSteps} />
          </div>
          <div className="p-5">
            <div className="flex items-center gap-2">
              <Gauge className="h-4 w-4 text-[#0028f3]" />
              <h4 className="font-semibold text-slate-950">CPK da regional</h4>
            </div>
            <div className="mt-4 rounded-2xl border bg-slate-50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Badge className={cpkBadgeClass(audit.cpk?.status)}>{audit.cpk?.status_label ?? "CPK não sincronizado"}</Badge>
                <span className={audit.cpk?.adjustment && audit.cpk.adjustment !== 0 ? "text-sm font-semibold text-[#0028f3]" : "text-sm font-semibold text-slate-500"}>
                  {formatMultiplier(audit.cpk?.adjustment)}
                </span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-xs text-slate-500">Realizado</p>
                  <p className="mt-1 font-semibold text-slate-950">{formatCpk(audit.cpk?.cpk_realizado)}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Meta</p>
                  <p className="mt-1 font-semibold text-slate-950">{formatCpk(audit.cpk?.cpk_meta)}</p>
                </div>
              </div>
              <p className="mt-4 text-sm text-slate-600">{audit.cpk?.description ?? "Não há dados de CPK para este fechamento."}</p>
              <p className="mt-3 text-xs text-slate-500">
                {audit.cpk?.mes_fechado ? "Snapshot de mês fechado." : "Snapshot parcial ou ainda não fechado."}
              </p>
            </div>
            <div className="mt-4 rounded-2xl border border-[#2d5fff]/15 bg-[#2d5fff]/5 p-4 text-sm text-slate-700">
              <div className="flex items-center gap-2 font-semibold text-slate-950">
                <ShieldCheck className="h-4 w-4 text-[#0028f3]" />
                Transparência do multiplicador
              </div>
              <p className="mt-2">
                O multiplicador final de {numberFormat.format(audit.health_multiplier)}x já considera saúde operacional e o ajuste de CPK quando aplicável.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-[#0028f3]" />
              <h4 className="font-semibold text-slate-950">Onde seus pontos nasceram</h4>
            </div>
            {groupData.length ? (
              <GroupBars groups={groupData} />
            ) : (
              <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">Ainda não há grupos com pontuação líquida neste período.</p>
            )}
          </div>
          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-[#0028f3]" />
              <h4 className="font-semibold text-slate-950">Evolução dos fechamentos</h4>
            </div>
            {audit.history.length ? (
              <HistoryList history={audit.history} />
            ) : (
              <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">Seu histórico aparecerá a partir dos próximos fechamentos.</p>
            )}
          </div>
      </section>
    </section>
  );
}
