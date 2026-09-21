// `import type`: os tipos do ExcelJS somem na compilação - o pacote de verdade (~900 KB) só é
// baixado quando alguém clica em exportar, mesmo padrão de `use-sla-export.ts`.
import type ExcelJS from "exceljs";
import { useCallback } from "react";

import type { OperationFilterState, OperationSlaMatrix } from "@/lib/operations-api";
import { regionalName } from "@/lib/regional";

const PERCENT_FORMAT = "0.0%";
const HOURS_FORMAT = "0.0";

const FILTER_LABELS: Array<[keyof OperationFilterState, string]> = [
  ["regionals", "Regional"],
  ["team_models", "Modelo de equipe"],
  ["os_types", "Tipo geral"],
  ["subjects", "Assunto"],
  ["responsibles", "Responsável"],
  ["sectors", "Setor"],
];

function describeFilters(filters: OperationFilterState) {
  const parts = [`Período: ${filters.date_from} até ${filters.date_to}`];
  for (const [key, label] of FILTER_LABELS) {
    const value = filters[key];
    if (!Array.isArray(value) || !value.length) continue;
    parts.push(`${label}: ${value.map((item) => (key === "regionals" ? regionalName(item) : item)).join(", ")}`);
  }
  return parts.join(" | ");
}

/** Mesmo formato de 3 linhas por indicador que a tela mostra (Realizadas/SLA/T.M. Fechamento) -
 * a planilha exportada é uma leitura fiel do que está na tela, não um resumo à parte. */
export function useSlaMatrixExport() {
  return useCallback(async (data: OperationSlaMatrix, filters: OperationFilterState) => {
    const { default: Excel } = await import("exceljs");
    const workbook = new Excel.Workbook();
    workbook.creator = "UNI Workspace";
    workbook.created = new Date();

    const sheet = workbook.addWorksheet("Matriz SLA");
    const headerRow = ["Card", "Indicador", "Métrica", ...data.regionals, "Matriz"];
    sheet.addRow(headerRow);
    sheet.getRow(1).font = { bold: true };

    for (const row of data.rows) {
      const cellByRegional = new Map(row.cells.map((cell) => [cell.regional, cell]));

      const completedRow = sheet.addRow([
        row.card_label,
        row.group_name,
        "Realizadas",
        ...data.regionals.map((regional) => cellByRegional.get(regional)?.completed ?? null),
        row.total.completed,
      ]);
      completedRow.font = { bold: true };

      const slaRow = sheet.addRow([
        row.card_label,
        row.group_name,
        "SLA",
        ...data.regionals.map((regional) => {
          const rate = cellByRegional.get(regional)?.sla_rate;
          return rate === undefined || rate === null ? null : rate / 100;
        }),
        row.total.sla_rate === null ? null : row.total.sla_rate / 100,
      ]);
      for (let index = 4; index <= headerRow.length; index += 1) slaRow.getCell(index).numFmt = PERCENT_FORMAT;

      const hoursRow = sheet.addRow([
        row.card_label,
        row.group_name,
        "T.M. fechamento (h)",
        ...data.regionals.map((regional) => cellByRegional.get(regional)?.average_closing_hours ?? null),
        row.total.average_closing_hours,
      ]);
      for (let index = 4; index <= headerRow.length; index += 1) hoursRow.getCell(index).numFmt = HOURS_FORMAT;
    }

    sheet.addRow([]);
    sheet.addRow(["Filtros aplicados:", describeFilters(filters)]);

    sheet.columns = [
      { width: 26 },
      { width: 32 },
      { width: 18 },
      ...data.regionals.map(() => ({ width: 16 })),
      { width: 14 },
    ];
    sheet.views = [{ state: "frozen", xSplit: 3, ySplit: 1 }];

    const buffer = await workbook.xlsx.writeBuffer();
    const blob = new Blob([buffer], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `matriz-sla-${filters.date_from}-a-${filters.date_to}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, []);
}
