"use client";

import {
  AlertTriangle,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  CircleDollarSign,
  ClipboardList,
  Download,
  MinusCircle,
  RefreshCw,
  Send,
  Trophy,
  UsersRound,
  Wallet,
  XCircle
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppMultiSelect } from "@/components/gamification/config-ui";
import { DashboardCharts } from "@/components/gamification/dashboard-charts";
import { FinancialTable } from "@/components/gamification/financial-table";
import { InfoHint } from "@/components/gamification/info-hint";
import type { ChartContext, ClosureBalanceImpact, ClosureFinancials, ClosureStatus } from "@/hooks/use-closure-data";
import { formatMoney, formatNumber, formatPoints, pluralizeFilial } from "@/lib/gamificacao-helpers";
import { normalizeRegional, regionalName } from "@/lib/regional";
import type { AuthUser, CollaboratorScore, DashboardSummary, PenaltyDistributionItem, RegionalHealthItem } from "@/lib/types";

const SECTION_HELP = {
  summary: "Consolida os valores principais do período, separando técnicos, liderança e total a pagar.",
  details: "Agrupa os blocos usados para conferência operacional e financeira do fechamento.",
  alerts: "Sinaliza inconsistências, itens sem regra ou pontos que exigem revisão.",
  leadership: "Resume o valor calculado para liderança com base no resultado auditado dos técnicos.",
  financial: "Mostra a decomposição dos valores do período por dimensão operacional.",
  financialRegional: "Distribui o valor estimado por regional dentro do recorte atual.",
  financialGroup: "Distribui o valor estimado por grupo ou tipo de serviço no recorte atual.",
  financialSubjects: "Aponta assuntos recorrentes que ainda não possuem regra aplicada.",
  chartArea: "Apresenta indicadores visuais para leitura rápida da saúde da base e do desempenho operacional.",
  filteredCharts: "Mostra os resultados considerando os filtros selecionados, como filial, regional ou período."
} as const;

function calculationStatusMeta(status: string | undefined) {
  switch (status) {
    case "review":
      return {
        label: "Em conferência",
        className: "w-fit border-amber-200 bg-white text-amber-700"
      };
    case "approved":
      return {
        label: "Aprovado",
        className: "w-fit border-sky-200 bg-white text-sky-700"
      };
    case "paid":
      return {
        label: "Pago",
        className: "w-fit border-emerald-200 bg-white text-emerald-700"
      };
    case "cancelled":
      return {
        label: "Cancelado",
        className: "w-fit border-rose-200 bg-white text-rose-700"
      };
    case "draft":
    default:
      return {
        label: "Rascunho",
        className: "w-fit border-slate-200 bg-white text-slate-700"
      };
  }
}

type DetailSection = "pending" | "leadership" | "financial" | "analysis";

export type ClosureTabProps = {
  summary: DashboardSummary;
  currentUser: AuthUser;
  can: (permission: string) => boolean;
  busy: boolean;
  closure: ClosureStatus;
  closureFinancials: ClosureFinancials;
  closureBalanceImpact: ClosureBalanceImpact;
  chartHealth: RegionalHealthItem[];
  chartContext: ChartContext;
  chartPenalties: PenaltyDistributionItem[];
  filteredRanking: CollaboratorScore[];
  filteredFinancials: {
    cost_by_regional: Array<Record<string, string | number | undefined>>;
    cost_by_group: Array<Record<string, string | number | undefined>>;
    top_unmapped_subjects: Array<Record<string, string | number | undefined>>;
  };
  financialCollapsed: boolean;
  onToggleFinancialCollapsed: () => void;
  selectedRegionals: string[];
  regionalOptions: string[];
  onSelectedRegionalsChange: (values: string[]) => void;
  leadershipCoveredRegionals: number;
  onExportPaymentCsv: () => void;
  onAdvanceRunStatus: (nextStatus: "review" | "approved" | "paid" | "cancelled", successMessage: string) => void | Promise<void>;
  onActiveTabChange: (tab: string) => void;
  onConfigTabChange: (tab: string) => void;
  onRankingTabChange: (tab: string) => void;
};

export function ClosureTab({
  summary,
  currentUser,
  can,
  busy,
  closure,
  closureFinancials,
  closureBalanceImpact,
  chartHealth,
  chartContext,
  chartPenalties,
  filteredRanking,
  filteredFinancials,
  financialCollapsed,
  onToggleFinancialCollapsed,
  selectedRegionals,
  regionalOptions,
  onSelectedRegionalsChange,
  leadershipCoveredRegionals,
  onExportPaymentCsv,
  onAdvanceRunStatus,
  onActiveTabChange,
  onConfigTabChange,
  onRankingTabChange
}: ClosureTabProps) {
  const [detailSection, setDetailSection] = useState<DetailSection>("pending");

  const sections: Array<{ key: DetailSection; label: string; badge: string; badgeTone: "warning" | "ok" | "neutral" | "accent" }> = [
    {
      key: "pending",
      label: "Pendências",
      badge: closure.pendingCount > 0 ? `${formatNumber(closure.pendingCount)}` : "OK",
      badgeTone: closure.pendingCount > 0 ? "warning" : "ok"
    },
    {
      key: "leadership",
      label: "Liderança",
      badge: formatMoney(summary.leadership_bonus?.total_bonus_amount ?? 0),
      badgeTone: "accent"
    },
    { key: "financial", label: "Financeiro", badge: "3 painéis", badgeTone: "neutral" },
    {
      key: "analysis",
      label: "Análise",
      badge: selectedRegionals.length ? `${selectedRegionals.length} ${pluralizeFilial(selectedRegionals.length)}` : "Todas",
      badgeTone: "neutral"
    }
  ];

  const badgeToneClass: Record<string, string> = {
    warning: "bg-amber-50 text-amber-700",
    ok: "bg-emerald-50 text-emerald-700",
    neutral: "bg-slate-100 text-slate-600",
    accent: "bg-[color:rgba(45,95,255,0.1)] text-[var(--uni-electric)]"
  };

  return (
    <div className="grid gap-4">
      <section className="relative overflow-hidden rounded-[24px] border border-slate-200/80 bg-white shadow-sm">
        <div className="uni-gradient h-[3px] w-full" />
        <div className="grid gap-5 p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                {closure.isClosed ? (
                  <Badge className={summary.run?.status === "paid" ? "w-fit border-emerald-200 bg-white text-emerald-700" : "w-fit border-rose-200 bg-white text-rose-700"}>
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {summary.run?.status === "paid" ? "Fechamento pago" : "Fechamento cancelado"}
                  </Badge>
                ) : (
                  <Badge
                    className={
                      closure.ready
                        ? "w-fit border-emerald-200 bg-white text-emerald-700"
                        : "w-fit border-amber-200 bg-white text-amber-700"
                    }
                  >
                    {closure.ready ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                    {closure.ready ? "Fechamento liberado" : "Fechamento com pendência"}
                  </Badge>
                )}
                <Badge className="w-fit border-slate-200 bg-white text-slate-700">
                  <CalendarDays className="h-3.5 w-3.5" />
                  {summary.run ? `${summary.run.reference_month}/${summary.run.reference_year}` : "Sem cálculo"}
                </Badge>
                {summary.run ? (
                  <Badge className={calculationStatusMeta(summary.run.status).className}>
                    <ClipboardList className="h-3.5 w-3.5" />
                    {calculationStatusMeta(summary.run.status).label}
                  </Badge>
                ) : null}
              </div>
              <div className="mt-3 flex items-center gap-2">
                <h2 className="text-2xl font-semibold leading-tight text-slate-950">
                  {closure.isClosed || closure.ready ? "Resumo financeiro da competência" : "Regras pendentes antes do pagamento"}
                </h2>
                <InfoHint
                  ariaLabel={`Ajuda sobre ${closure.isClosed || closure.ready ? "Resumo financeiro da competência" : "Regras pendentes antes do pagamento"}`}
                  description={SECTION_HELP.summary}
                />
              </div>
              {closure.isClosed && closure.pendingCount > 0 ? (
                <p className="mt-2 text-sm text-amber-700">
                  Este fechamento tinha {formatNumber(closure.pendingCount)} pendência(s) de governança registrada(s) no momento do pagamento. Veja abaixo.
                </p>
              ) : null}
              {summary.run?.status_note ? (
                <p className="mt-2 text-sm text-slate-500">{summary.run.status_note}</p>
              ) : null}
            </div>
            <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
              {currentUser.role !== "viewer" ? (
                <Button type="button" variant="outline" onClick={onExportPaymentCsv} className="w-full bg-white sm:w-auto">
                  <Download className="h-4 w-4" />
                  Exportar pagamento
                </Button>
              ) : null}
              {summary.run && can("calculation:run") ? (
                <>
                  {summary.run.status === "draft" ? (
                    <Button
                      type="button"
                      onClick={() => onAdvanceRunStatus("review", "Fechamento enviado para conferência.")}
                      disabled={busy}
                      className="w-full bg-amber-600 text-white hover:bg-amber-700 sm:w-auto"
                    >
                      <Send className="h-4 w-4" />
                      Enviar para conferência
                    </Button>
                  ) : null}
                  {summary.run.status === "review" && currentUser.role === "admin" ? (
                    <Button
                      type="button"
                      onClick={() => onAdvanceRunStatus("approved", "Fechamento aprovado.")}
                      disabled={busy}
                      className="w-full bg-sky-600 text-white hover:bg-sky-700 sm:w-auto"
                    >
                      <CheckCircle2 className="h-4 w-4" />
                      Aprovar fechamento
                    </Button>
                  ) : null}
                  {summary.run.status === "approved" && currentUser.role === "admin" ? (
                    <Button
                      type="button"
                      onClick={() => onAdvanceRunStatus("paid", "Fechamento marcado como pago.")}
                      disabled={busy}
                      className="w-full bg-emerald-600 text-white hover:bg-emerald-700 sm:w-auto"
                    >
                      <Wallet className="h-4 w-4" />
                      Marcar como pago
                    </Button>
                  ) : null}
                  {["draft", "review", "approved"].includes(summary.run.status) ? (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => onAdvanceRunStatus("cancelled", "Fechamento cancelado.")}
                      disabled={busy}
                      className="w-full bg-white text-rose-600 hover:bg-rose-50 sm:w-auto"
                    >
                      <XCircle className="h-4 w-4" />
                      Cancelar
                    </Button>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(260px,340px)]">
            <div>
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <span className="inline-block h-3 w-[3px] rounded-full bg-[var(--uni-cyan)]" />
                Total a pagar no período
              </div>
              <div className="mt-1 truncate text-[40px] font-semibold leading-none text-slate-950">
                {formatMoney(closureFinancials.totalAmount)}
              </div>
              <div className="mt-2 text-sm text-slate-500">
                <span className="font-semibold text-slate-800">{formatMoney(closureFinancials.technicianAmount)}</span> técnicos
                {" + "}
                <span className="font-semibold text-slate-800">{formatMoney(closureFinancials.leadershipAmount)}</span> liderança
              </div>
            </div>

            <div className="divide-y divide-slate-100 rounded-[16px] border border-slate-100 bg-slate-50/60 px-4">
              <div className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <span className="flex items-center gap-2 text-slate-500">
                  <ClipboardList className="h-3.5 w-3.5" />
                  O.S no período
                </span>
                <span className="font-semibold text-slate-900">{formatNumber(summary.cards.total_service_orders)} O.S</span>
              </div>
              <div className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <span className="flex items-center gap-2 text-slate-500">
                  <BarChart3 className="h-3.5 w-3.5" />
                  Pontos finais
                </span>
                <span className="font-semibold text-slate-900">{formatPoints(summary.cards.final_points)}</span>
              </div>
              <div className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <span className="flex items-center gap-2 text-slate-500">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  Pontos anulados
                </span>
                <span className={`font-semibold ${summary.cards.penalty_points > 0 ? "text-red-700" : "text-slate-900"}`}>
                  {formatNumber(summary.cards.penalty_points)} pts
                </span>
              </div>
              {closureBalanceImpact.collaboratorCount > 0 ? (
                <button
                  type="button"
                  onClick={() => onActiveTabChange("balance")}
                  className="flex w-full items-center justify-between gap-3 py-2.5 text-left text-sm transition hover:text-red-800"
                >
                  <span className="flex items-center gap-2 text-red-700">
                    <MinusCircle className="h-3.5 w-3.5" />
                    Descontos de garantia
                  </span>
                  <span className="font-semibold text-red-700">
                    {formatPoints(Math.abs(closureBalanceImpact.points))} · {formatNumber(closureBalanceImpact.collaboratorCount)} colab.
                  </span>
                </button>
              ) : (
                <div className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="flex items-center gap-2 text-slate-500">
                    <MinusCircle className="h-3.5 w-3.5" />
                    Descontos de garantia
                  </span>
                  <span className="font-semibold text-slate-900">Sem descontos</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
        <div className="border-b bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] px-5 py-4">
          <div className="flex items-center gap-2">
            <h2 className="text-[16px] font-semibold leading-tight text-slate-950">Detalhamento do fechamento</h2>
            <InfoHint ariaLabel="Ajuda sobre Detalhamento do fechamento" description={SECTION_HELP.details} />
          </div>
          <div className="mt-3 flex overflow-hidden rounded-xl border border-slate-200">
            {sections.map((section) => {
              const active = detailSection === section.key;
              return (
                <button
                  key={section.key}
                  type="button"
                  onClick={() => setDetailSection(section.key)}
                  className={
                    active
                      ? "flex flex-1 items-center justify-center gap-2 border-l border-slate-200 bg-[var(--uni-royal)] px-3 py-2 text-[12px] font-semibold text-white first:border-l-0"
                      : "flex flex-1 items-center justify-center gap-2 border-l border-slate-200 bg-white px-3 py-2 text-[12px] font-semibold text-slate-500 transition hover:bg-slate-50 first:border-l-0"
                  }
                >
                  {section.label}
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                      active ? "bg-white/20 text-white" : badgeToneClass[section.badgeTone]
                    }`}
                  >
                    {section.badge}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="p-5">
          {detailSection === "pending" ? (
            <div>
              <div className="mb-3 flex items-center gap-2">
                <InfoHint ariaLabel="Ajuda sobre Alertas e pendências" description={SECTION_HELP.alerts} />
                <span className="text-sm text-slate-500">
                  {closure.isClosed ? "Pendências registradas no fechamento" : "Alertas e pendências que impedem o fechamento"}
                </span>
              </div>
              {closure.pendingCount > 0 ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {closure.pendingItems.map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.label}
                        className="rounded-[18px] border border-slate-200 bg-white p-4 text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:border-blue-300 hover:bg-blue-50/40"
                        onClick={() => {
                          onActiveTabChange(item.tab);
                          if ("configSubTab" in item && item.configSubTab) onConfigTabChange(item.configSubTab);
                        }}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className={item.value > 0 ? "text-2xl font-semibold text-amber-700" : "text-2xl font-semibold text-emerald-700"}>
                            {formatNumber(item.value)}
                          </div>
                          <div
                            className={
                              item.value > 0
                                ? "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-amber-50 text-amber-700"
                                : "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700"
                            }
                          >
                            <Icon className="h-4 w-4" />
                          </div>
                        </div>
                        <div className="mt-1 text-sm font-semibold text-slate-950">{item.label}</div>
                        <div className="mt-2 text-xs text-slate-500">{item.help}</div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="flex items-center gap-3 rounded-lg border bg-emerald-50/60 px-4 py-4 text-sm text-slate-700">
                  <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                  Todas as O.S do período possuem regra de assunto ou diagnóstico aplicada.
                </div>
              )}
            </div>
          ) : null}

          {detailSection === "leadership" ? (
            <div>
              <div className="mb-3 flex items-center gap-2">
                <InfoHint ariaLabel="Ajuda sobre Bonificação de liderança" description={SECTION_HELP.leadership} />
                <span className="text-sm text-slate-500">Bonificação de liderança</span>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                {[
                  ["Valor da liderança", formatMoney(summary.leadership_bonus?.total_bonus_amount ?? 0)],
                  ["Perfis ativos", `${formatNumber(summary.leadership_bonus?.results.length ?? 0)} líder(es)`],
                  ["Filiais cobertas", `${formatNumber(leadershipCoveredRegionals)} ${pluralizeFilial(leadershipCoveredRegionals)}`]
                ].map(([label, value]) => (
                  <div key={label} className="rounded-[18px] border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</div>
                    <div className="mt-2 text-xl font-semibold text-slate-950">{value}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-col gap-3 rounded-[20px] border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-sm font-semibold text-slate-950">Ranking de liderança separado do fechamento</div>
                  <p className="mt-1 text-sm text-slate-500">
                    A lista detalhada de líderes agora fica na aba Ranking, em uma visão própria para comparação e conferência.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-xl border-slate-300"
                  onClick={() => {
                    onActiveTabChange("ranking");
                    onRankingTabChange("leaders");
                  }}
                >
                  Ver ranking de líderes
                </Button>
              </div>
            </div>
          ) : null}

          {detailSection === "financial" ? (
            <div>
              <div className="mb-3 flex items-center gap-2">
                <InfoHint ariaLabel="Ajuda sobre Detalhamento financeiro" description={SECTION_HELP.financial} />
                <span className="text-sm text-slate-500">Detalhamento financeiro por dimensão operacional</span>
              </div>
              <div className="grid min-w-0 gap-4 xl:grid-cols-3">
                <FinancialTable
                  title="Valor a ser pago por regional"
                  rows={filteredFinancials.cost_by_regional}
                  labelKey="regional"
                  collapsed={financialCollapsed}
                  onToggle={onToggleFinancialCollapsed}
                  helpText={SECTION_HELP.financialRegional}
                />
                <FinancialTable
                  title="Valor a ser pago por grupo"
                  rows={filteredFinancials.cost_by_group}
                  labelKey="group"
                  collapsed={financialCollapsed}
                  onToggle={onToggleFinancialCollapsed}
                  helpText={SECTION_HELP.financialGroup}
                />
                <FinancialTable
                  title="Assuntos sem regra frequentes"
                  rows={filteredFinancials.top_unmapped_subjects}
                  labelKey="os_subject"
                  collapsed={financialCollapsed}
                  onToggle={onToggleFinancialCollapsed}
                  helpText={SECTION_HELP.financialSubjects}
                />
              </div>
            </div>
          ) : null}

          {detailSection === "analysis" ? (
            <div>
              <div className="mb-3 flex items-center gap-2">
                <InfoHint ariaLabel="Ajuda sobre Análise operacional e gráficos" description={SECTION_HELP.chartArea} />
                <span className="text-sm text-slate-500">Análise operacional e gráficos</span>
              </div>
              <div className="grid gap-4 rounded-[20px] border border-slate-200 bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] p-4 lg:grid-cols-[1fr_minmax(260px,360px)] lg:items-start">
                <div>
                  <Badge className="w-fit border-slate-200 bg-white text-slate-700">
                    <BarChart3 className="h-3.5 w-3.5" />
                    Análise operacional
                  </Badge>
                  <div className="mt-2 flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-slate-950">Gráficos e indicadores filtrados</h2>
                    <InfoHint ariaLabel="Ajuda sobre Gráficos e indicadores filtrados" description={SECTION_HELP.filteredCharts} />
                  </div>
                </div>
                <AppMultiSelect
                  values={selectedRegionals}
                  onChange={onSelectedRegionalsChange}
                  options={regionalOptions.map((regional) => ({ value: normalizeRegional(regional), label: regionalName(regional) }))}
                  placeholder="Todas as filiais"
                  searchPlaceholder="Buscar regional"
                  ariaLabel="Filtrar por regional"
                />
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  { label: "Contexto", value: chartContext.label, icon: BarChart3, tone: "text-slate-950" },
                  { label: "Colaboradores", value: `${formatNumber(chartContext.collaborators)} colaboradores`, icon: UsersRound, tone: "text-slate-950" },
                  { label: "Reincidências", value: `${formatNumber(chartContext.recurrenceOrders)} O.S`, icon: AlertTriangle, tone: "text-amber-700" },
                  { label: "% reincidência", value: `${formatNumber(chartContext.recurrenceRate)}%`, icon: RefreshCw, tone: "text-blue-700" }
                ].map((item) => {
                  const Icon = item.icon;
                  return (
                    <div key={item.label} className="rounded-md border bg-white px-3 py-2 shadow-sm">
                      <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                        <Icon className="h-3.5 w-3.5" />
                        <span className="truncate">{item.label}</span>
                      </div>
                      <div className={`mt-1 truncate text-sm font-semibold ${item.tone}`}>{item.value}</div>
                    </div>
                  );
                })}
              </div>

              <div className="mt-4">
                <DashboardCharts ranking={filteredRanking} penalties={chartPenalties} health={chartHealth} />
              </div>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
