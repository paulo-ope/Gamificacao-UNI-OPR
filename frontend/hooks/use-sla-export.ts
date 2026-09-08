// `import type`: os tipos (Fill, Worksheet, Workbook) somem na compilação. O ExcelJS de verdade
// (~900 KB) só é baixado quando alguém clica em exportar - antes ele vinha no bundle inicial da
// tela, e ainda duplicado entre módulos (achado medido no bundle de produção em 2026-09-03).
import type ExcelJS from "exceljs";
import { useCallback } from "react";

import {
  operationsApi,
  type OperationFilterState,
  type OperationSlaHierarchy,
  type OperationSlaHierarchyLevel,
} from "@/lib/operations-api";
import { regionalName } from "@/lib/regional";

const HEADERS = [
  "Tipo Geral",
  "Assunto",
  "Realizadas",
  "SLA Técnico",
  "Até 12h",
  "12h-24h",
  "24h-48h",
  "48h-72h",
  "Após 72h",
  "T.M. Fech. (h)",
];

const PERCENT_FORMAT = "0.0%";
const HOURS_FORMAT = "0.00";

const FILTER_LABELS: Array<[keyof OperationFilterState, string]> = [
  ["regionals", "Regional"],
  ["team_models", "Modelo de equipe"],
  ["os_types", "Tipo geral"],
  ["subjects", "Assunto"],
  ["responsibles", "Responsável"],
  ["companies", "Empresa / filial"],
  ["states", "UF"],
  ["cities", "Cidade"],
  ["statuses", "Status"],
  ["priorities", "Prioridade"],
  ["diagnoses", "Diagnóstico"],
  ["person_types", "Tipo de pessoa"],
  ["contract_types", "Tipo de contrato"],
  ["departments", "Departamento"],
  ["sectors", "Setor"],
  ["creators", "Criador da O.S."],
  ["projects", "Projeto"],
  ["pops", "POP"],
  ["sla_statuses", "Situação do SLA"],
];

function filterOptionLabel(key: keyof OperationFilterState, value: string) {
  if (key === "regionals") return regionalName(value);
  if (key === "sla_statuses") {
    if (value === "on_time") return "No prazo";
    if (value === "out_of_time") return "Fora do prazo";
    return "Não identificada";
  }
  return value;
}

function describeFilters(filters: OperationFilterState) {
  const parts = [
    `Período: ${filters.date_from} até ${filters.date_to}`,
  ];
  for (const [key, label] of FILTER_LABELS) {
    const value = filters[key];
    if (!Array.isArray(value) || !value.length) continue;
    parts.push(
      `${label}: ${value.map((item) => filterOptionLabel(key, item)).join(", ")}`,
    );
  }
  return parts.join(" | ");
}

function percentValue(rate: number | null) {
  return rate === null ? null : rate / 100;
}

function addDataRow(
  sheet: ExcelJS.Worksheet,
  tipoGeral: string,
  item: {
    label: string;
    completed: number;
    sla_rate: number | null;
    up_to_12h_rate: number | null;
    from_12h_to_24h_rate: number | null;
    from_24h_to_48h_rate: number | null;
    from_48h_to_72h_rate: number | null;
    after_72h_rate: number | null;
    average_closing_hours: number | null;
  },
) {
  const row = sheet.addRow([
    tipoGeral,
    item.label,
    item.completed,
    percentValue(item.sla_rate),
    percentValue(item.up_to_12h_rate),
    percentValue(item.from_12h_to_24h_rate),
    percentValue(item.from_24h_to_48h_rate),
    percentValue(item.from_48h_to_72h_rate),
    percentValue(item.after_72h_rate),
    item.average_closing_hours,
  ]);
  for (const columnIndex of [4, 5, 6, 7, 8, 9]) {
    row.getCell(columnIndex).numFmt = PERCENT_FORMAT;
  }
  row.getCell(10).numFmt = HOURS_FORMAT;
  return row;
}

export function useSlaExport() {
  return useCallback(
    async (
      level: OperationSlaHierarchyLevel,
      data: OperationSlaHierarchy,
      filters: OperationFilterState,
    ) => {
      const { default: Excel } = await import("exceljs");
      const workbook = new Excel.Workbook();
      workbook.creator = "UNI Workspace";
      workbook.created = new Date();

      const sheet = workbook.addWorksheet("Export");
      sheet.addRow(HEADERS);
      sheet.getRow(1).font = { bold: true };

      if (level === "os_type") {
        // Agrupado por Tipo Geral: uma linha "Total" por tipo, seguida dos assuntos daquele
        // tipo - espelha exatamente a hierarquia expansível da tela quando "Tipo geral" está
        // selecionado no agrupamento.
        const subjectsByType = await Promise.all(
          data.items.map((typeItem) =>
            operationsApi.slaHierarchy(filters, "subject", typeItem.label),
          ),
        );
        data.items.forEach((typeItem, index) => {
          addDataRow(sheet, typeItem.label, { ...typeItem, label: "Total" });
          subjectsByType[index].items.forEach((subjectItem) => {
            addDataRow(sheet, typeItem.label, subjectItem);
          });
        });
      } else {
        // "Assunto" ou "Diagnóstico" selecionados: a tela mostra uma lista achatada (sem
        // agrupar por Tipo Geral) - a exportação segue o mesmo recorte, coluna Tipo Geral fica
        // vazia nas linhas de detalhe.
        data.items.forEach((item) => addDataRow(sheet, "", item));
      }

      addDataRow(sheet, "", { ...data.total, label: "Total geral" });

      sheet.addRow([]);
      sheet.addRow(["Filtros aplicados:", describeFilters(filters)]);

      sheet.columns = [
        { width: 24 },
        { width: 28 },
        { width: 12 },
        { width: 12 },
        { width: 10 },
        { width: 10 },
        { width: 10 },
        { width: 10 },
        { width: 10 },
        { width: 14 },
      ];

      const buffer = await workbook.xlsx.writeBuffer();
      const blob = new Blob([buffer], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `sla-${filters.date_from}-a-${filters.date_to}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
    [],
  );
}
