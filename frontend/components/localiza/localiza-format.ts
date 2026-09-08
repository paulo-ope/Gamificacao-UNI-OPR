import type { Tone } from "@/lib/tones";
import type { LocationRequestStatus } from "@/lib/localiza-api";

export { formatDateTime as formatPortoVelho } from "@/lib/format";

// O código da O.S. costuma não existir ainda quando o link é gerado (enviado antes de abrir o
// atendimento no IXC) - esta função dá o melhor identificador disponível pra exibir em qualquer
// tela (listagem, painel de detalhe, página pública do cliente), nesta ordem de preferência.
export function localizaRequestLabel(item: {
  order_code: string | null;
  opa_protocol: string | null;
  customer_name: string | null;
  public_id: string;
}): string {
  if (item.order_code) return `O.S. ${item.order_code}`;
  if (item.opa_protocol) return `Protocolo OPA ${item.opa_protocol}`;
  if (item.customer_name) return item.customer_name;
  return `Solicitação ${item.public_id}`;
}

export const LOCALIZA_STATUS_LABELS: Record<LocationRequestStatus, string> = {
  pending: "Pendente",
  confirmed: "Confirmado",
  invalidated: "Invalidado",
  expired: "Expirado"
};

export const LOCALIZA_STATUS_TONE: Record<LocationRequestStatus, Tone> = {
  pending: "amber",
  confirmed: "emerald",
  invalidated: "slate",
  expired: "red"
};
