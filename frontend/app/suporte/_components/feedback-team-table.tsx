"use client";

import type { SupportFeedback, SupportMacroCardStatus } from "@/lib/types";

import { formatCardValue } from "./dashboard-format";
import { STATUS_LABEL, periodTargetLabel } from "./feedback-format";

// Visão da equipe toda do Feedback (pedido do usuário, 2026-10-27): sem colaborador escolhido, uma listra por pessoa
// com o resultado de cada indicador, colorido pelo status. Os valores e status vêm prontos do backend.

const VALUE_TONE: Record<SupportMacroCardStatus, string> = {
  ok: "text-emerald-700",
  attention: "text-amber-700",
  critical: "text-red-600",
  partial: "text-slate-500",
  no_data: "text-slate-400",
  no_target: "text-slate-700",
};

const STATUS_BADGE: Record<SupportMacroCardStatus, string> = {
  ok: "bg-emerald-600 text-white",
  attention: "bg-amber-400 text-amber-950",
  critical: "bg-red-500 text-white",
  partial: "bg-slate-200 text-slate-700",
  no_data: "bg-slate-200 text-slate-700",
  no_target: "bg-slate-200 text-slate-700",
};

export function FeedbackTeamTable({ team, onSelect }: { team: SupportFeedback[]; onSelect: (attendantId: string) => void }) {
  if (!team.length) {
    return <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">Nenhum colaborador na equipe do Suporte.</div>;
  }
  const columns = team[0].indicators;
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full min-w-[900px] text-sm">
        <thead>
          <tr className="bg-sky-100 text-left text-[10px] uppercase tracking-wide text-slate-600">
            <th className="px-3 py-2 font-semibold">Colaborador</th>
            <th className="px-3 py-2 font-semibold">Status</th>
            {columns.map((column) => (
              <th key={column.key} className="px-3 py-2 font-semibold">
                {column.label}
                <span className="block text-[10px] font-normal normal-case tracking-normal text-slate-500">{periodTargetLabel(column)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {team.map((person) => (
            <tr
              key={person.attendant_id}
              onClick={() => onSelect(person.attendant_id)}
              className="cursor-pointer border-t border-slate-100 odd:bg-white even:bg-slate-50 hover:bg-sky-50"
            >
              <td className="px-3 py-2">
                <button type="button" onClick={() => onSelect(person.attendant_id)} className="text-left font-semibold text-slate-900 hover:underline">
                  {person.name}
                </button>
              </td>
              <td className="px-3 py-2">
                <span className={`inline-block rounded-full px-2.5 py-0.5 text-[11px] font-bold ${STATUS_BADGE[person.summary.overall as SupportMacroCardStatus]}`}>
                  {STATUS_LABEL[person.summary.overall as SupportMacroCardStatus]}
                </span>
              </td>
              {person.indicators.map((indicator) => (
                <td key={indicator.key} className={`px-3 py-2 font-bold tabular-nums ${VALUE_TONE[indicator.status as SupportMacroCardStatus]}`}>
                  {formatCardValue(indicator, indicator.value)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
