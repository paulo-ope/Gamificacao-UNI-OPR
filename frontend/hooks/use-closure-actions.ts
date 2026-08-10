import ExcelJS from "exceljs";
import { useCallback } from "react";

import { formatMoney, formatNumber, formatPoints, leadershipAverageSourceLabel, leadershipRoleLabel } from "@/lib/gamificacao-helpers";
import { api } from "@/lib/api";
import { normalizeRegional, regionalName } from "@/lib/regional";
import type { AuthUser, DashboardSummary } from "@/lib/types";

const SECTION_HEADER_FILL: ExcelJS.Fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF0F172A" } };
const TABLE_HEADER_FILL: ExcelJS.Fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFE2E8F0" } };

const CPK_STATUS_LABEL: Record<string, string> = {
  na_meta: "Na meta",
  fora_meta: "Fora da meta",
  sem_base: "Sem base"
};

function sheetNameFactory() {
  const used = new Set<string>();
  return (label: string) => {
    // Excel proibe : \ / ? * [ ] no nome da aba e limita a 31 caracteres - "UNI - " e o hifen
    // repetem em toda regional, sem valor nenhum dentro da aba (a aba ja e a regional).
    const base = (label.replace(/^UNI\s*-\s*/i, "").trim() || "Regional").replace(/[:\\/?*\[\]]/g, "").slice(0, 31);
    let name = base;
    let attempt = 2;
    while (used.has(name.toLowerCase())) {
      const suffix = ` ${attempt}`;
      name = `${base.slice(0, 31 - suffix.length)}${suffix}`;
      attempt += 1;
    }
    used.add(name.toLowerCase());
    return name;
  };
}

function addSectionTable(
  sheet: ExcelJS.Worksheet,
  title: string,
  headers: string[],
  rows: (string | number)[][],
  totalsRow?: (string | number)[]
) {
  const titleRow = sheet.addRow([title]);
  titleRow.font = { bold: true, color: { argb: "FFFFFFFF" } };
  titleRow.eachCell((cell) => {
    cell.fill = SECTION_HEADER_FILL;
  });

  const headerRow = sheet.addRow(headers);
  headerRow.font = { bold: true };
  headerRow.eachCell((cell) => {
    cell.fill = TABLE_HEADER_FILL;
  });

  if (rows.length === 0) {
    sheet.addRow(["Nenhum registro nesta regional."]);
  } else {
    rows.forEach((row) => sheet.addRow(row));
  }

  if (totalsRow && rows.length > 0) {
    const row = sheet.addRow(totalsRow);
    row.font = { bold: true };
  }

  sheet.addRow([]);
}

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

  const exportPaymentWorkbook = useCallback(async () => {
    if (!summary || currentUser?.role === "viewer") return;
    // "Desconto de saldo" mistura todo tipo de ajuste aplicado (garantia + manual + saldo
    // remanescente) - quem confere o pagamento (e a auditoria) precisa distinguir quanto disso
    // e especificamente debito de garantia, ja que os outros tipos tem motivo/origem diferentes.
    const garantiaDiscountByCollaborator = new Map<number, number>();
    if (summary.run?.id) {
      const balanceEntries = await api.pointBalancePending({ calculation_run_id: summary.run.id });
      balanceEntries
        .filter((entry) => entry.bucket === "applied" && entry.entry_type === "post_payment_warranty_debit")
        .forEach((entry) => {
          garantiaDiscountByCollaborator.set(
            entry.collaborator_id,
            (garantiaDiscountByCollaborator.get(entry.collaborator_id) ?? 0) + entry.points
          );
        });
    }
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

    // Gerente de pasta (portfolio_manager) sempre vai pra aba Matriz, mesmo quando tem regionais
    // especificas vinculadas no cadastro (ex.: cobre 11 das 14 regionais) - misturar o bonus dele
    // numa dessas abas confundia quem fechava o pagamento so daquela regional, que via um valor
    // grande sem relacao com o time local. So supervisor/gerente de unidade entram nas abas por
    // regional.
    const regionalLeadershipPool = leadershipRows.filter((item) => item.role_type !== "portfolio_manager");
    const matrizLeadershipRows = leadershipRows.filter((item) => item.role_type === "portfolio_manager");

    // Uma aba por regional (o motivo de existir esta funcao) - reune toda regional que aparece em
    // qualquer uma das 3 tabelas, mesmo que so tenha lideranca ou so tenha pendente de cadastro.
    const regionals = new Set<string>();
    paymentRows.forEach((score) => regionals.add(normalizeRegional(score.regional)));
    regionalLeadershipPool.forEach((item) => item.regionals.forEach((regional) => regionals.add(normalizeRegional(regional))));
    pendingRows.forEach((item) => regionals.add(normalizeRegional(item.suggested_regional || item.regional)));
    const sortedRegionals = Array.from(regionals).sort((a, b) => regionalName(a).localeCompare(regionalName(b), "pt-BR"));

    const workbook = new ExcelJS.Workbook();
    workbook.creator = "UNI Workspace";
    const nextSheetName = sheetNameFactory();
    // Um lider que cobre varias regionais (ex.: gerente de pasta, ou supervisor multi-filial)
    // aparecia numa linha por regional coberta, repetindo o MESMO valor a pagar em cada aba - quem
    // fosse pagar podia somar o valor por aba e pagar o mesmo bonus varias vezes por engano.
    // Cada lideranca agora aparece uma unica vez no arquivo inteiro (na primeira regional dela em
    // ordem alfabetica), com a coluna "Regionais" mostrando todas as areas que ela cobre.
    const placedLeadershipIds = new Set<number>();

    for (const regional of sortedRegionals) {
      const sheet = workbook.addWorksheet(nextSheetName(regionalName(regional)));
      sheet.views = [{ state: "frozen", ySplit: 1 }];

      const titleRow = sheet.addRow([`Pagamento - ${regionalName(regional)}`]);
      titleRow.font = { bold: true, size: 13 };
      sheet.addRow([]);

      const regionalPaymentRows = paymentRows.filter((score) => normalizeRegional(score.regional) === regional);
      addSectionTable(
        sheet,
        "Pagamento de técnicos",
        [
          "Colaborador", "O.S", "Pontos brutos", "Pontos anulados", "Pontos líquidos", "Desconto de saldo",
          "Desconto de garantia", "SLA da base (%)", "CPK da base", "Multiplicador saúde", "Pontos finais", "Valor a ser pago"
        ],
        regionalPaymentRows.map((score) => {
          const regionalHealth = healthByRegional.get(normalizeRegional(score.regional));
          const cpkLabel = regionalHealth?.cpk_status ? CPK_STATUS_LABEL[regionalHealth.cpk_status] ?? "-" : "-";
          return [
            score.collaborator_name,
            formatNumber(score.service_orders_count),
            formatPoints(score.gross_points),
            formatPoints(score.penalty_points),
            formatPoints(score.net_points),
            formatPoints(score.balance_adjustment_points),
            formatPoints(garantiaDiscountByCollaborator.get(score.collaborator_id) ?? 0),
            regionalHealth ? `${formatNumber(regionalHealth.sla_rate)}%` : "-",
            cpkLabel,
            `${formatNumber(score.health_multiplier)}x`,
            formatPoints(score.final_points),
            formatMoney(score.estimated_payment)
          ];
        }),
        [
          "Total", "", "", "",
          "", formatPoints(regionalPaymentRows.reduce((sum, score) => sum + score.balance_adjustment_points, 0)),
          formatPoints(regionalPaymentRows.reduce((sum, score) => sum + (garantiaDiscountByCollaborator.get(score.collaborator_id) ?? 0), 0)),
          "", "", "", "",
          formatMoney(regionalPaymentRows.reduce((sum, score) => sum + score.estimated_payment, 0))
        ]
      );

      const regionalLeadershipRows = regionalLeadershipPool.filter(
        (item) => !placedLeadershipIds.has(item.leadership_profile_id) && item.regionals.some((r) => normalizeRegional(r) === regional)
      );
      regionalLeadershipRows.forEach((item) => placedLeadershipIds.add(item.leadership_profile_id));
      addSectionTable(
        sheet,
        "Bonificação de liderança",
        ["Liderança", "Regionais", "Tipo", "Origem da média", "Pessoas na média", "Soma dos pontos", "Média final", "Multiplicador", "Valor a ser pago"],
        regionalLeadershipRows.map((item) => [
          item.name,
          item.regionals.map((r) => regionalName(r)).join(", "),
          leadershipRoleLabel(item.role_type),
          leadershipAverageSourceLabel(item.average_source),
          formatNumber(item.audit?.scoped_collaborators ?? item.scoped_collaborators),
          `${formatNumber(item.audit?.total_final_points ?? item.average_final_points * item.scoped_collaborators)} pts`,
          `${formatNumber(item.average_final_points)} pts`,
          `${formatNumber(item.multiplier)}x`,
          formatMoney(item.bonus_amount)
        ])
      );

      const regionalPendingRows = pendingRows.filter((item) => normalizeRegional(item.suggested_regional || item.regional) === regional);
      addSectionTable(
        sheet,
        "Pendentes de cadastro",
        ["Nome identificado", "O.S", "Valor potencial", "Status"],
        regionalPendingRows.map((item) => [item.name, `${formatNumber(item.service_orders_count)} O.S`, formatMoney(item.estimated_payment), "Pendente de cadastro"])
      );

      sheet.columns.forEach((column) => {
        column.width = 22;
      });
    }

    // Gerente de pasta (portfolio_manager) sempre cai aqui (ver filtro de regionalLeadershipPool
    // acima), mais qualquer outra lideranca sem filial vinculada no cadastro - sem esta aba, o
    // bonus dela simplesmente desapareceria do arquivo em vez de aparecer repetido. Nome "Matriz"
    // (nao "Liderança Geral") para deixar explicito que nao e uma regional operacional - decisao
    // do usuario para nao confundir quem esta fechando o pagamento por filial.
    const leftoverLeadershipRows = [
      ...matrizLeadershipRows,
      ...regionalLeadershipPool.filter((item) => !placedLeadershipIds.has(item.leadership_profile_id)),
    ];
    if (leftoverLeadershipRows.length > 0) {
      const sheet = workbook.addWorksheet(nextSheetName("Matriz"));
      sheet.views = [{ state: "frozen", ySplit: 1 }];
      const titleRow = sheet.addRow(["Matriz - gerência de pasta e liderança sem filial específica"]);
      titleRow.font = { bold: true, size: 13 };
      sheet.addRow([]);
      addSectionTable(
        sheet,
        "Bonificação de liderança",
        ["Liderança", "Regionais", "Tipo", "Origem da média", "Pessoas na média", "Soma dos pontos", "Média final", "Multiplicador", "Valor a ser pago"],
        leftoverLeadershipRows.map((item) => [
          item.name,
          item.regionals.length > 0 ? item.regionals.map((r) => regionalName(r)).join(", ") : "Toda a operação",
          leadershipRoleLabel(item.role_type),
          leadershipAverageSourceLabel(item.average_source),
          formatNumber(item.audit?.scoped_collaborators ?? item.scoped_collaborators),
          `${formatNumber(item.audit?.total_final_points ?? item.average_final_points * item.scoped_collaborators)} pts`,
          `${formatNumber(item.average_final_points)} pts`,
          `${formatNumber(item.multiplier)}x`,
          formatMoney(item.bonus_amount)
        ])
      );
      sheet.columns.forEach((column) => {
        column.width = 22;
      });
    }

    const buffer = await workbook.xlsx.writeBuffer();
    const blob = new Blob([buffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `pagamentos-gamificação-${summary.run?.reference_month ?? "período"}-${summary.run?.reference_year ?? "atual"}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, [currentUser?.role, selectedRegionals, summary]);

  return { advanceRunStatus, exportPaymentWorkbook };
}
