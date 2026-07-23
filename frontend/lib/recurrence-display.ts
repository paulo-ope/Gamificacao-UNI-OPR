import type { Tone } from "@/lib/tones";

// Campos mínimos necessários para resolver a etiqueta de retorno de uma O.S. - subconjunto de
// CollaboratorOrderDetail (types.ts), aceito estruturalmente para servir também aos itens de
// timeline/related_orders da auditoria de reincidência.
export type RecurrenceDisplaySource = {
  recurrence_classification: string | null;
  recurrence_rule_name?: string | null;
  is_warranty: boolean;
  is_recurrence: boolean;
};

export type RecurrenceDisplay = { label: string; tone: Tone };

// Rótulos genéricos APENAS para classificações internas sem regra configurada. Quando existe uma
// regra (recurrence_rule_name), o nome configurado pelo usuário na tela de regras é exibido como
// está - decisão do dono do produto: a auditoria respeita o nome dado à regra, sem apelidos fixos
// do frontend (antes "garantia" era sempre reescrito para "Reincidência após ativação").
const FALLBACK_CLASSIFICATION_LABELS: Record<string, string> = {
  recorrencia_operacional: "Recorrência operacional",
  reincidencia_tecnica: "Reincidência técnica",
  garantia: "Garantia",
  possivel_retorno_sem_regra: "Retorno na janela sem regra ativa",
  os_nao_reincidente: "O.S. não reincidente",
  demandas_diferentes: "Demandas diferentes",
  nao_identificado: "Não identificado"
};

const NON_RETURN_CLASSIFICATIONS = new Set(["os_nao_reincidente", "demandas_diferentes", "nao_identificado"]);

export function recurrenceClassificationLabel(value: string | null | undefined) {
  if (!value) return "Sem classificação";
  return FALLBACK_CLASSIFICATION_LABELS[value] ?? value;
}

// Regra de etiqueta única: uma O.S. exibe no máximo UMA etiqueta de retorno.
// Precedência: nome da regra configurada > rótulo genérico da classificação > flags legadas de
// planilha (garantia vence reincidência quando as duas colunas vieram marcadas) > nenhuma.
export function resolveRecurrenceDisplay(order: RecurrenceDisplaySource): RecurrenceDisplay | null {
  if (order.recurrence_classification) {
    if (NON_RETURN_CLASSIFICATIONS.has(order.recurrence_classification)) return null;
    const label = order.recurrence_rule_name || recurrenceClassificationLabel(order.recurrence_classification);
    return { label, tone: "blue" };
  }
  if (order.is_warranty) return { label: "Garantia (importada)", tone: "blue" };
  if (order.is_recurrence) return { label: "Reincidência (importada)", tone: "blue" };
  return null;
}

function safeText(value: string | null | undefined) {
  return value === null || value === undefined || value === "" ? "Não informado" : String(value);
}

// Só correções de acento/grafia de textos vindos do backend - NÃO renomeia mais "Garantia" para
// "Reincidência" (a reescrita antiga contradizia o nome que o usuário configurou nas regras).
export function cleanOperationalText(value: string | null | undefined) {
  return safeText(value)
    .replace(/reincidencia/gi, "reincidência")
    .replace(/pontuacao/gi, "pontuação")
    .replace(/revisao/gi, "revisão")
    .replace(/Reducao/gi, "Redução");
}
