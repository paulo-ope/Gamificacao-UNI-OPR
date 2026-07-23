import { useCallback } from "react";

import { formatMoney, formatNumber, formatPoints, leadershipAverageSourceLabel, leadershipRoleLabel } from "@/lib/gamificacao-helpers";
import { api } from "@/lib/api";
import { normalizeRegional, regionalName } from "@/lib/regional";
import type { AuthUser, DashboardSummary } from "@/lib/types";

type ClosurePeriod = { reference_month?: number; reference_year?: number; regional?: string | null };

type ConfirmOptions = {
  title?: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
};

type UseClosureActionsParams = {
  summary: DashboardSummary | null;
  currentUser: AuthUser | null;
  selectedRegionals: string[];
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  withFeedback: <T>(action: () => Promise<T>, success: string | (() => string)) => Promise<T | undefined>;
  setError: (message: string | null) => void;
  loadAll: (period?: ClosurePeriod, options?: { refreshRuleBasics?: boolean }) => Promise<void>;
  setHistoryLoaded: (value: boolean) => void;
};

export function useClosureActions({
  summary,
  currentUser,
  selectedRegionals,
  confirm,
  withFeedback,
  setError,
  loadAll,
  setHistoryLoaded
}: UseClosureActionsParams) {
  const advanceRunStatus = useCallback(
    async (nextStatus: "review" | "approved" | "paid" | "cancelled", successMessage: string) => {
      const runId = summary?.run?.id;
      if (!runId) {
        setError("Nenhum fechamento calculado para avançar o status. Recalcule o período primeiro.");
        return;
      }
      if (nextStatus === "paid") {
        const confirmed = await confirm({
          title: "Marcar como pago",
          description:
            "Marcar este fechamento como PAGO é definitivo e não pode ser revertido. " +
            "A partir daqui, débitos de garantia pendentes dos colaboradores serão aplicados. Deseja continuar?",
          confirmLabel: "Marcar como pago",
          tone: "danger"
        });
        if (!confirmed) return;
      }
      if (nextStatus === "cancelled") {
        const confirmed = await confirm({
          title: "Cancelar fechamento",
          description: "Cancelar este fechamento? Ele não poderá mais ser aprovado ou pago.",
          confirmLabel: "Cancelar fechamento",
          tone: "danger"
        });
        if (!confirmed) return;
      }
      await withFeedback(async () => {
        await api.updateCalculationRunStatus(runId, { status: nextStatus });
        const period = {
          reference_month: summary?.run?.reference_month,
          reference_year: summary?.run?.reference_year,
          regional: summary?.run?.regional
        };
        await loadAll(period, { refreshRuleBasics: false });
        setHistoryLoaded(false);
      }, successMessage);
    },
    [confirm, loadAll, setError, setHistoryLoaded, summary?.run?.id, summary?.run?.reference_month, summary?.run?.reference_year, summary?.run?.regional, withFeedback]
  );

  const exportPaymentCsv = useCallback(() => {
    if (!summary || currentUser?.role === "viewer") return;
    const healthByRegional = new Map(summary.health_by_regional.map((item) => [normalizeRegional(item.regional), item]));
    const paymentRows = summary.ranking.filter((score) => {
      const matchesRegional = selectedRegionals.length === 0 || selectedRegionals.includes(normalizeRegional(score.regional));
      return matchesRegional && score.is_registered !== false;
    });
    const leadershipRows = (summary.leadership_bonus?.results ?? []).filter((item) => {
      return selectedRegionals.length === 0 || item.regionals.some((regional) => selectedRegionals.includes(normalizeRegional(regional)));
    });
    const pendingRows = (summary.leadership_bonus?.pending_collaborators ?? []).filter((item) => {
      return selectedRegionals.length === 0 || selectedRegionals.includes(normalizeRegional(item.suggested_regional || item.regional));
    });
    const rows = [
      ["Pagamento de técnicos"],
      [
        "Colaborador",
        "Regional",
        "Tipo",
        "O.S",
        "Pontos brutos",
        "Pontos anulados",
        "Pontos líquidos",
        "SLA da base (%)",
        "Multiplicador saúde",
        "Pontos finais",
        "Valor a ser pago"
      ],
      ...paymentRows.map((score) => {
        const regionalHealth = healthByRegional.get(normalizeRegional(score.regional));
        return [
          score.collaborator_name,
          regionalName(score.regional),
          "Técnico",
          formatNumber(score.service_orders_count),
          formatPoints(score.gross_points),
          formatPoints(score.penalty_points),
          formatPoints(score.net_points),
          regionalHealth ? `${formatNumber(regionalHealth.sla_rate)}%` : "-",
          `${formatNumber(score.health_multiplier)}x`,
          formatPoints(score.final_points),
          formatMoney(score.estimated_payment)
        ];
      }),
      [],
      ["Bonificação de liderança"],
      [
        "Liderança",
        "Regionais",
        "Tipo",
        "Origem da média",
        "Pessoas na média",
        "Soma dos pontos",
        "Média final",
        "Multiplicador",
        "Valor a ser pago"
      ],
      ...leadershipRows.map((item) => [
        item.name,
        item.regionals.map((regional) => regionalName(regional)).join(", "),
        leadershipRoleLabel(item.role_type),
        leadershipAverageSourceLabel(item.average_source),
        formatNumber(item.audit?.scoped_collaborators ?? item.scoped_collaborators),
        `${formatNumber(item.audit?.total_final_points ?? item.average_final_points * item.scoped_collaborators)} pts`,
        `${formatNumber(item.average_final_points)} pts`,
        `${formatNumber(item.multiplier)}x`,
        formatMoney(item.bonus_amount)
      ]),
      [],
      ["Pendentes de cadastro"],
      ["Nome identificado", "Regional sugerida", "O.S", "Valor potencial", "Status"],
      ...pendingRows.map((item) => [
        item.name,
        regionalName(item.suggested_regional || item.regional),
        `${formatNumber(item.service_orders_count)} O.S`,
        formatMoney(item.estimated_payment),
        "Pendente de cadastro"
      ])
    ];
    const csv = rows.map((row) => row.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(";")).join("\r\n");
    const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `pagamentos-gamificação-${summary.run?.reference_month ?? "período"}-${summary.run?.reference_year ?? "atual"}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, [currentUser?.role, selectedRegionals, summary]);

  return { advanceRunStatus, exportPaymentCsv };
}
