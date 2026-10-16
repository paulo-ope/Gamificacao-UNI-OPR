import type { SupportFeedbackIndicator, SupportMacroCardStatus } from "@/lib/types";

import { formatCardValue } from "./dashboard-format";

// Textos e rótulos do Feedback individual, compartilhados entre a tela e o PDF (`feedback-print.ts`).

export const STATUS_LABEL: Record<SupportMacroCardStatus, string> = {
  ok: "Dentro da Meta",
  attention: "Atenção",
  critical: "Evoluir",
  partial: "Dado parcial",
  no_data: "Sem dado",
  no_target: "Sem meta",
};

// Como acompanhar o indicador no próximo ciclo (texto de apoio da conversa; a meta em si vem do backend).
export const FOLLOW_UP: Record<string, string> = {
  operational: "Conferir o volume de registros operacionais no meio do turno e corrigir a rota antes do fechamento do dia.",
  financial: "Conferir o volume de registros financeiros no meio do turno e corrigir a rota antes do fechamento do dia.",
  field: "Revisar as O.S. abertas a campo e confirmar se o atendimento remoto foi esgotado antes de abrir.",
  opa_attendances: "Acompanhar a disponibilidade na fila e manter o volume de atendimentos ao longo da semana.",
  calls: "Manter o ramal disponível e priorizar a ligação como primeiro contato.",
  rating: "Fechar o atendimento confirmando a solução com o cliente para melhorar a avaliação.",
  tma: "Acompanhar a fila com mais frequência e evitar atendimentos sem tratativa registrada.",
  tmr: "Responder o cliente com mais agilidade e evitar longos intervalos sem retorno.",
};

export const dateBr = (iso: string) => iso.split("-").reverse().join("/");

const prefix = (indicator: SupportFeedbackIndicator) => (indicator.direction === "min" ? "Mínimo" : "Até");

/** Meta semanal original ("Mínimo 38", "Até 00:02:20"). */
export function weeklyTargetLabel(indicator: SupportFeedbackIndicator) {
  return `${prefix(indicator)} ${formatCardValue(indicator, indicator.weekly_target)}`;
}

/** Meta já ajustada ao período escolhido. */
export function periodTargetLabel(indicator: SupportFeedbackIndicator) {
  return `${prefix(indicator)} ${formatCardValue(indicator, indicator.target)}`;
}
