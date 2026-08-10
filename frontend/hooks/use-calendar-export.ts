import ExcelJS from "exceljs";
import { useCallback } from "react";

import type { OperationCalendar, OperationCalendarCollaborator, OperationCalendarTeamModel } from "@/lib/operations-api";
import { customBackground, dayTarget, modelLegend, performanceLabel, ruleFor } from "@/lib/operations-calendar-helpers";
import { regionalName } from "@/lib/regional";

const WEEKDAYS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"];

const TITLE_FILL: ExcelJS.Fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF0F172A" } };
const HEADER_FILL: ExcelJS.Fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF1E293B" } };
const WEEKEND_FILL: ExcelJS.Fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFF1F5F9" } };
const UNAVAILABLE_FILL: ExcelJS.Fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFE2E8F0" } };
const THIN_BORDER: Partial<ExcelJS.Borders> = {
  top: { style: "thin", color: { argb: "FFCBD5E1" } },
  left: { style: "thin", color: { argb: "FFCBD5E1" } },
  bottom: { style: "thin", color: { argb: "FFCBD5E1" } },
  right: { style: "thin", color: { argb: "FFCBD5E1" } },
};

// ExcelJS quer ARGB (8 dígitos); as cores do modelo de equipe vêm em "#rrggbb" (6 dígitos, ver
// HEX_COLOR_PATTERN em operations/schemas.py) - só prefixar a opacidade total.
function toArgb(hex: string) {
  return `FF${hex.replace("#", "").toUpperCase()}`;
}

function sheetNameFactory() {
  const used = new Set<string>();
  return (label: string) => {
    const base = (label.replace(/^UNI\s*-\s*/i, "").trim() || "Regional").replace(/[:\\/?*[\]]/g, "").slice(0, 31);
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

function competenceLabel(competence: string) {
  const [year, month] = competence.split("-").map(Number);
  if (!year || !month) return competence;
  return new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(year, month - 1, 1)));
}

function modelSummary(collaborator: OperationCalendarCollaborator) {
  if (!collaborator.team_model) return "Sem modelo de equipe";
  const target = ruleFor(collaborator.team_model, "weekday")?.target_quantity ?? collaborator.team_model.daily_target;
  return `${collaborator.team_model.name} · meta ${target}/dia`;
}

function buildRegionalSheet(workbook: ExcelJS.Workbook, nextSheetName: (label: string) => string, data: OperationCalendar, regional: OperationCalendar["regionals"][number]) {
  const sheet = workbook.addWorksheet(nextSheetName(regional.regional));

  const titleRow = sheet.addRow([`Calendário operacional · ${regionalName(regional.regional)} · ${competenceLabel(data.competence)}`]);
  titleRow.font = { bold: true, color: { argb: "FFFFFFFF" }, size: 12 };
  titleRow.eachCell((cell) => {
    cell.fill = TITLE_FILL;
  });
  sheet.mergeCells(titleRow.number, 1, titleRow.number, data.days.length + 3);
  sheet.addRow([]);

  // Congela nome + modelo (2 colunas) e as duas linhas de cabeçalho, para rolar os dias sem perder
  // de vista quem é a linha nem o que representa cada coluna - mesmo recurso que a tela usa com
  // `sticky`.
  const headerRowNumber = titleRow.number + 3;
  sheet.views = [{ state: "frozen", xSplit: 2, ySplit: headerRowNumber }];

  const dayHeaderRow = sheet.addRow(["Colaborador", "Modelo / meta", ...data.days.map((day) => day.day), "Total"]);
  const weekdayHeaderRow = sheet.addRow(["", "", ...data.days.map((day) => WEEKDAYS[day.weekday]), ""]);
  [dayHeaderRow, weekdayHeaderRow].forEach((row) => {
    row.font = { bold: true, color: { argb: "FFE2E8F0" } };
    row.eachCell((cell) => {
      cell.fill = HEADER_FILL;
      cell.alignment = { horizontal: "center", vertical: "middle" };
    });
  });
  dayHeaderRow.getCell(1).alignment = { horizontal: "left" };
  weekdayHeaderRow.getCell(1).alignment = { horizontal: "left" };

  regional.collaborators.forEach((collaborator) => {
    const row = sheet.addRow([
      collaborator.responsible,
      modelSummary(collaborator),
      ...data.days.map((day) => {
        if (!day.available) return null;
        return collaborator.daily_counts[day.date] || null;
      }),
      collaborator.total,
    ]);
    row.getCell(1).font = { bold: true };
    row.eachCell((cell) => {
      cell.border = THIN_BORDER;
      cell.alignment = { horizontal: "center", vertical: "middle" };
    });
    row.getCell(1).alignment = { horizontal: "left" };
    row.getCell(2).alignment = { horizontal: "left" };

    data.days.forEach((day, index) => {
      const cell = row.getCell(index + 3);
      if (!day.available) {
        cell.fill = UNAVAILABLE_FILL;
        return;
      }
      const performance = collaborator.daily_performance[day.date] || "neutral";
      const color = customBackground(performance, collaborator.team_model);
      if (color) {
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: toArgb(color) } };
      } else if (day.weekday >= 5) {
        cell.fill = WEEKEND_FILL;
      }
      const target = dayTarget(collaborator.team_model, day.weekday);
      cell.note = `${performanceLabel(performance, collaborator.daily_counts[day.date] || 0, collaborator.team_model)}${target ? ` · meta ${target.target_quantity}` : " · sem meta neste dia"}`;
    });

    const totalCell = row.getCell(data.days.length + 3);
    const totalColor = customBackground(collaborator.monthly_performance, collaborator.team_model);
    if (totalColor) totalCell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: toArgb(totalColor) } };
    totalCell.font = { bold: true };
  });

  sheet.addRow([]);
  const legendModels = new Map<number, OperationCalendarTeamModel>();
  regional.collaborators.forEach((collaborator) => {
    if (collaborator.team_model) legendModels.set(collaborator.team_model.id, collaborator.team_model);
  });
  if (legendModels.size) {
    const legendTitle = sheet.addRow(["Legenda de desempenho por modelo de equipe"]);
    legendTitle.font = { bold: true };
    Array.from(legendModels.values()).forEach((model) => {
      const legendRow = sheet.addRow([model.name]);
      modelLegend(model).forEach((band) => {
        const cell = legendRow.getCell(legendRow.cellCount + 1);
        cell.value = band.label;
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: toArgb(band.color) } };
        cell.border = THIN_BORDER;
      });
    });
  }

  sheet.getColumn(1).width = 28;
  sheet.getColumn(2).width = 26;
  for (let index = 0; index < data.days.length; index += 1) {
    sheet.getColumn(index + 3).width = 5;
  }
  sheet.getColumn(data.days.length + 3).width = 10;
}

export function useCalendarExport() {
  return useCallback(async (data: OperationCalendar) => {
    if (!data.regionals.length) return;
    const workbook = new ExcelJS.Workbook();
    workbook.creator = "UNI Workspace";
    workbook.created = new Date();

    const nextSheetName = sheetNameFactory();
    data.regionals.forEach((regional) => buildRegionalSheet(workbook, nextSheetName, data, regional));

    const buffer = await workbook.xlsx.writeBuffer();
    const blob = new Blob([buffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `calendario-operacional-${data.competence}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, []);
}
