import { HelpCircle, ShieldAlert, UsersRound } from "lucide-react";
import { useMemo, useState } from "react";

import { normalizeRegional, regionalName } from "@/lib/regional";
import type { CollaboratorScore, DashboardSummary, RegionalHealthItem } from "@/lib/types";

export type ClosurePendingItem = {
  label: string;
  value: number;
  tab: "pending" | "config";
  configSubTab?: "collaborators";
  icon: typeof HelpCircle;
  help: string;
};

export type ClosureStatus = {
  ready: boolean;
  pendingCount: number;
  pendingItems: ClosurePendingItem[];
  isClosed: boolean;
};

export type ClosureFinancials = {
  technicianAmount: number;
  leadershipAmount: number;
  totalAmount: number;
};

export type ClosureBalanceImpact = {
  collaboratorCount: number;
  points: number;
};

export type ChartContext = {
  serviceOrders: number;
  recurrenceOrders: number;
  recurrenceRate: number;
  collaborators: number;
  label: string;
};

export type ClosureDerivedData = {
  closure: ClosureStatus;
  closureFinancials: ClosureFinancials;
  closureBalanceImpact: ClosureBalanceImpact;
  chartHealth: RegionalHealthItem[];
  chartContext: ChartContext;
};

function deriveClosure(summary: DashboardSummary | null): ClosureStatus {
  if (!summary) {
    return {
      ready: false,
      pendingCount: 0,
      pendingItems: [],
      isClosed: false
    };
  }

  const pendingItems: ClosurePendingItem[] = [
    {
      label: "O.S sem regra de pontuação",
      value: summary.cards.unscored_service_orders,
      tab: "pending",
      icon: HelpCircle,
      help: "Assuntos importados que ainda não estão vinculados a um grupo."
    },
    {
      label: "Diagnósticos sem regra",
      value: summary.cards.diagnosis_unmapped_service_orders,
      tab: "pending",
      icon: ShieldAlert,
      help: "Diagnósticos encontrados sem regra de liberação ou anulação."
    },
    {
      label: "Colaboradores pendentes de cadastro",
      value: summary.leadership_bonus?.pending_collaborators.length ?? 0,
      tab: "config",
      configSubTab: "collaborators",
      icon: UsersRound,
      help: "Colaboradores com produção no período que ainda não estão formalmente cadastrados."
    }
  ];
  const pendingCount = pendingItems.reduce((total, item) => total + item.value, 0);
  const isClosed = summary.run?.status === "paid" || summary.run?.status === "cancelled";

  return {
    ready: pendingCount === 0,
    pendingCount,
    pendingItems,
    isClosed
  };
}

function deriveClosureFinancials(summary: DashboardSummary | null): ClosureFinancials {
  const technicianAmount = summary?.cards.estimated_payment ?? 0;
  const leadershipAmount = summary?.leadership_bonus?.total_bonus_amount ?? 0;
  return {
    technicianAmount,
    leadershipAmount,
    totalAmount: technicianAmount + leadershipAmount
  };
}

function deriveClosureBalanceImpact(summary: DashboardSummary | null): ClosureBalanceImpact {
  const affected = (summary?.ranking ?? []).filter((score: CollaboratorScore) => (score.balance_adjustment_points ?? 0) < 0);
  return {
    collaboratorCount: affected.length,
    points: affected.reduce((total, score) => total + (score.balance_adjustment_points ?? 0), 0)
  };
}

function deriveChartHealth(summary: DashboardSummary | null, selectedRegionals: string[]): RegionalHealthItem[] {
  if (!summary) return [];
  return selectedRegionals.length > 0
    ? summary.health_by_regional.filter((item) => selectedRegionals.includes(normalizeRegional(item.regional)))
    : summary.health_by_regional;
}

function deriveChartContext(chartHealth: RegionalHealthItem[], filteredRankingLength: number, selectedRegionals: string[]): ChartContext {
  const serviceOrders = chartHealth.reduce((total, item) => total + item.total_orders, 0);
  const recurrenceOrders = chartHealth.reduce((total, item) => total + (item.recurrence_orders ?? 0), 0);
  const recurrenceRate = serviceOrders > 0 ? (recurrenceOrders / serviceOrders) * 100 : 0;
  return {
    serviceOrders,
    recurrenceOrders,
    recurrenceRate,
    collaborators: filteredRankingLength,
    label:
      selectedRegionals.length === 0
        ? "Todas as regionais"
        : selectedRegionals.length === 1
          ? regionalName(selectedRegionals[0])
          : `${selectedRegionals.length} regionais`
  };
}

export function deriveClosureData(
  summary: DashboardSummary | null,
  selectedRegionals: string[],
  filteredRankingLength: number
): ClosureDerivedData {
  const chartHealth = deriveChartHealth(summary, selectedRegionals);
  return {
    closure: deriveClosure(summary),
    closureFinancials: deriveClosureFinancials(summary),
    closureBalanceImpact: deriveClosureBalanceImpact(summary),
    chartHealth,
    chartContext: deriveChartContext(chartHealth, filteredRankingLength, selectedRegionals)
  };
}

export function useClosureData(summary: DashboardSummary | null, selectedRegionals: string[], filteredRankingLength: number) {
  const [financialCollapsed, setFinancialCollapsed] = useState(true);

  const data = useMemo(
    () => deriveClosureData(summary, selectedRegionals, filteredRankingLength),
    [summary, selectedRegionals, filteredRankingLength]
  );

  return {
    ...data,
    financialCollapsed,
    setFinancialCollapsed
  };
}
