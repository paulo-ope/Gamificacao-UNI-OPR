"use client";

import { BarChart3, CheckCircle2, CircleDollarSign, ClipboardList, HelpCircle, MapPin, Search, Trophy, UsersRound, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AppMultiSelect } from "@/components/gamification/config-ui";
import { Input } from "@/components/ui/input";
import { RankingTable } from "@/components/gamification/ranking-table";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatMoney, formatNumber, formatPoints, leadershipAverageSourceLabel, leadershipRoleLabel, pluralizeFilial } from "@/lib/gamificacao-helpers";
import { normalizeRegional, regionalName } from "@/lib/regional";
import type { CollaboratorScore, DashboardSummary, LeadershipBonusResult } from "@/lib/types";

function summarizeLabels(items: string[], visibleCount = 2) {
  if (items.length <= visibleCount) return { visible: items, remaining: 0 };
  return { visible: items.slice(0, visibleCount), remaining: items.length - visibleCount };
}

type StatRow = { label: string; value: string; icon: typeof ClipboardList; tone: "neutral" | "good" | "warning" | "info" };

const STAT_TONE_CLASS: Record<StatRow["tone"], string> = {
  neutral: "bg-slate-100 text-slate-600",
  good: "bg-emerald-50 text-emerald-700",
  warning: "bg-amber-50 text-amber-700",
  info: "bg-[color:rgba(45,95,255,0.1)] text-[var(--uni-electric)]"
};

function StatStrip({ rows }: { rows: StatRow[] }) {
  return (
    <div className="grid divide-y divide-slate-100 rounded-[14px] border border-slate-200 bg-white sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-5">
      {rows.map((row) => {
        const Icon = row.icon;
        return (
          <div key={row.label} className="flex items-center gap-2 px-3 py-2.5">
            <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${STAT_TONE_CLASS[row.tone]}`}>
              <Icon className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-500">{row.label}</div>
              <div className="truncate text-sm font-semibold text-slate-950">{row.value}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export type RankingTabProps = {
  summary: DashboardSummary;
  selectedRegionals: string[];
  regionalOptions: string[];
  onSelectedRegionalsChange: (values: string[]) => void;
  rankingSearch: string;
  onRankingSearchChange: (value: string) => void;
  rankingTab: string;
  onRankingTabChange: (value: string) => void;
  filteredRanking: CollaboratorScore[];
  rankingScopeTotals: {
    serviceOrders: number;
    scored: number;
    unscored: number;
    annulled: number;
    estimated: number;
  };
  outsideRankingCount: number;
  filteredLeadershipResults: LeadershipBonusResult[];
  leadershipScopeTotals: {
    leaders: number;
    scopedCollaborators: number;
    averageMultiplier: number;
    baseAmount: number;
    bonusAmount: number;
  };
  leadershipCoveredRegionals: number;
  onViewOrders: (score: CollaboratorScore) => void;
  onAuditLeadership: (result: LeadershipBonusResult) => void;
};

export function RankingTab({
  summary,
  selectedRegionals,
  regionalOptions,
  onSelectedRegionalsChange,
  rankingSearch,
  onRankingSearchChange,
  rankingTab,
  onRankingTabChange,
  filteredRanking,
  rankingScopeTotals,
  outsideRankingCount,
  filteredLeadershipResults,
  leadershipScopeTotals,
  leadershipCoveredRegionals,
  onViewOrders,
  onAuditLeadership
}: RankingTabProps) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <section className="panel flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="shrink-0 border-b bg-gradient-to-r from-slate-50 via-white to-white px-4 py-4">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="min-w-0">
              <Badge className="w-fit border-slate-200 bg-white text-slate-700">
                <Trophy className="h-3.5 w-3.5" />
                Ranking operacional
              </Badge>
              <h2 className="mt-2 text-xl font-semibold text-slate-950">Colaboradores por resultado final</h2>
              <p className="mt-1 text-sm text-slate-500">
                Referência {summary.run?.reference_month}/{summary.run?.reference_year}. Valor global{" "}
                {formatMoney(summary.run?.point_value ?? summary.point_value)}.
              </p>
            </div>
            <div className="grid gap-2 xl:min-w-[420px]">
              <AppMultiSelect
                values={selectedRegionals}
                onChange={onSelectedRegionalsChange}
                options={regionalOptions.map((regional) => ({ value: normalizeRegional(regional), label: regionalName(regional) }))}
                placeholder="Todas as filiais"
                searchPlaceholder="Buscar regional"
                ariaLabel="Filtrar por regional"
              />
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                <Input
                  className="h-9 pl-9"
                  value={rankingSearch}
                  onChange={(event) => onRankingSearchChange(event.target.value)}
                  placeholder={rankingTab === "collaborators" ? "Buscar colaborador" : "Buscar líder ou perfil"}
                />
              </div>
            </div>
          </div>

          <Tabs value={rankingTab} onValueChange={onRankingTabChange} className="mt-4 grid gap-4">
            <div className="rounded-xl border border-slate-200 bg-white p-2">
              <TabsList className="flex h-auto flex-wrap justify-start gap-2 bg-transparent p-0">
                <TabsTrigger value="collaborators">Colaboradores</TabsTrigger>
                <TabsTrigger value="leaders">Liderança</TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="collaborators" className="mt-0 grid gap-3">
              <p className="text-xs text-slate-500">
                <span className="font-medium text-slate-800">{formatNumber(rankingScopeTotals.serviceOrders)} O.S entraram no ranking</span>
                {" · "}
                {formatNumber(outsideRankingCount)} O.S ficaram fora.
                {rankingSearch.trim() ? " A busca por nome filtra a lista abaixo, mas não altera este resumo." : ""}
              </p>
              <StatStrip
                rows={[
                  { label: "O.S no ranking", value: `${formatNumber(rankingScopeTotals.serviceOrders)} O.S`, icon: ClipboardList, tone: "neutral" },
                  { label: "Fora do ranking", value: `${formatNumber(outsideRankingCount)} O.S`, icon: XCircle, tone: outsideRankingCount > 0 ? "warning" : "good" },
                  { label: "O.S pontuadas", value: `${formatNumber(rankingScopeTotals.scored)} O.S`, icon: CheckCircle2, tone: "good" },
                  { label: "O.S sem regra", value: `${formatNumber(rankingScopeTotals.unscored)} O.S`, icon: HelpCircle, tone: rankingScopeTotals.unscored > 0 ? "warning" : "good" },
                  { label: "Valor a ser pago", value: formatMoney(rankingScopeTotals.estimated), icon: CircleDollarSign, tone: "info" }
                ]}
              />
            </TabsContent>

            <TabsContent value="leaders" className="mt-0 grid gap-3">
              <p className="text-xs text-slate-500">
                <span className="font-medium text-slate-800">{formatNumber(filteredLeadershipResults.length)} líder(es) no recorte</span>
                {" · "}
                {formatNumber(leadershipCoveredRegionals)} {pluralizeFilial(leadershipCoveredRegionals, " coberta")}.
                {rankingSearch.trim() ? " A busca filtra a tabela abaixo, sem alterar o resumo financeiro do período." : ""}
              </p>
              <StatStrip
                rows={[
                  { label: "Líderes no ranking", value: `${formatNumber(leadershipScopeTotals.leaders)} líder(es)`, icon: Trophy, tone: "info" },
                  { label: "Filiais cobertas", value: `${formatNumber(leadershipCoveredRegionals)} ${pluralizeFilial(leadershipCoveredRegionals)}`, icon: MapPin, tone: "neutral" },
                  { label: "Colaboradores na base", value: `${formatNumber(leadershipScopeTotals.scopedCollaborators)} colaborador(es)`, icon: UsersRound, tone: "neutral" },
                  { label: "Multiplicador médio", value: leadershipScopeTotals.leaders ? `${formatNumber(leadershipScopeTotals.averageMultiplier)}x` : "0x", icon: BarChart3, tone: "neutral" },
                  { label: "Valor a pagar", value: formatMoney(leadershipScopeTotals.bonusAmount), icon: CircleDollarSign, tone: "info" }
                ]}
              />
            </TabsContent>
          </Tabs>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {rankingTab === "collaborators" ? (
            <RankingTable data={filteredRanking} onViewOrders={onViewOrders} />
          ) : (
            <div className="table-frame h-full overflow-auto px-2 py-2">
              <div className="rounded-xl border border-slate-200 bg-white">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-950">Ranking de liderança</div>
                    <div className="text-xs text-slate-500">Ordenado pelo valor a pagar no recorte atual.</div>
                  </div>
                  <Badge className="border-slate-200 bg-slate-50 text-slate-700">
                    Base financeira {formatMoney(leadershipScopeTotals.baseAmount)}
                  </Badge>
                </div>
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-slate-900 text-white shadow-sm [&_th]:text-slate-200">
                    <TableRow className="border-slate-700 hover:bg-slate-900">
                      <TableHead>Líder</TableHead>
                      <TableHead>Perfil</TableHead>
                      <TableHead>Filiais cobertas</TableHead>
                      <TableHead>Base</TableHead>
                      <TableHead>Média final</TableHead>
                      <TableHead>Multiplicador</TableHead>
                      <TableHead className="text-right">Valor a pagar</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredLeadershipResults.map((item) => {
                      const normalizedRegionals = item.regionals.map((regional) => regionalName(regional));
                      const regionalSummary = summarizeLabels(normalizedRegionals);
                      const roleLabel = leadershipRoleLabel(item.role_type);
                      const profileLabel =
                        item.role_profile_name && item.role_profile_name !== roleLabel ? item.role_profile_name : roleLabel;
                      return (
                        <TableRow key={`${item.leadership_profile_id}-${item.role_type}`}>
                          <TableCell className="min-w-[220px]">
                            <div className="grid gap-1">
                              <div className="font-semibold text-slate-950">{item.name}</div>
                              <div className="text-xs text-slate-500">{profileLabel}</div>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge className="border-[color:rgba(45,95,255,0.25)] bg-[color:rgba(45,95,255,0.08)] text-[var(--uni-electric)]">{profileLabel}</Badge>
                          </TableCell>
                          <TableCell className="min-w-[280px]">
                            <div className="flex flex-wrap gap-1.5">
                              {regionalSummary.visible.map((regional) => (
                                <Badge key={`${item.leadership_profile_id}-${regional}`} className="border-slate-200 bg-slate-50 text-slate-700">
                                  {regional}
                                </Badge>
                              ))}
                              {regionalSummary.remaining > 0 ? (
                                <Badge className="border-slate-200 bg-white text-slate-500">+{regionalSummary.remaining}</Badge>
                              ) : null}
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="grid gap-0.5">
                              <span className="font-medium text-slate-900">{formatNumber(item.scoped_collaborators)} pessoa(s)</span>
                              <span className="text-xs text-slate-500">{leadershipAverageSourceLabel(item.average_source)} - {formatMoney(item.base_amount)}</span>
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="grid gap-2">
                              <span className="font-medium text-slate-950">{formatPoints(item.average_final_points)}</span>
                              <Button
                                type="button"
                                size="sm"
                                className="h-8 w-fit rounded-full border border-[var(--uni-royal)] bg-[var(--uni-royal)] px-3 text-[11px] font-semibold text-white shadow-sm hover:bg-[var(--uni-electric)]"
                                onClick={() => onAuditLeadership(item)}
                              >
                                <Search className="h-3.5 w-3.5" />
                                Auditar média
                              </Button>
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="grid gap-0.5">
                              <span className="font-medium text-slate-900">{formatNumber(item.multiplier)}x</span>
                              <span className="text-xs text-slate-500">{item.point_value > 0 ? `${formatMoney(item.point_value)}/pt` : "Sem valor"}</span>
                            </div>
                          </TableCell>
                          <TableCell className="text-right">
                            <span className="font-semibold text-uni-royal">{formatMoney(item.bonus_amount)}</span>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                    {filteredLeadershipResults.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-10 text-center text-sm text-slate-500">
                          Nenhum líder encontrado para os filtros atuais.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
