import type { MetricCards } from "@/lib/types";

const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/**
 * Quantidade de O.S. do período que a gamificação de fato remunera: só as executadas por equipe
 * cadastrada. É o número principal das telas do módulo.
 *
 * Não recalcula nada - escolhe qual campo já entregue pela API apresentar (norma §2). O `??` cobre
 * respostas de uma versão anterior do backend, que não mandava `registered_service_orders`; nesse
 * caso volta ao total, que é o comportamento antigo, em vez de mostrar zero.
 */
export function registeredServiceOrders(cards: Pick<MetricCards, "total_service_orders" | "registered_service_orders">) {
  return cards.registered_service_orders ?? cards.total_service_orders ?? 0;
}

/** O.S. do período executadas por técnico SEM cadastro - nunca entram no ranking nem no pagamento. */
export function unregisteredServiceOrders(
  cards: Pick<MetricCards, "total_service_orders" | "registered_service_orders" | "unregistered_service_orders">
) {
  if (cards.unregistered_service_orders !== undefined) return cards.unregistered_service_orders;
  if (cards.registered_service_orders === undefined) return 0;
  return Math.max((cards.total_service_orders ?? 0) - cards.registered_service_orders, 0);
}

export function formatNumber(value: number) {
  return numberFormat.format(value);
}

export function formatMoney(value: number) {
  return moneyFormat.format(value);
}

export function formatPoints(value: number) {
  return `${formatNumber(value)} pts`;
}

export function leadershipRoleLabel(value: string) {
  if (value === "supervisor") return "Supervisor";
  if (value === "regional_manager") return "Gerente da unidade";
  if (value === "portfolio_manager") return "Gerente de pasta";
  return value;
}

export function leadershipAverageSourceLabel(value: string | undefined) {
  if (value === "collaborators_and_leaders") return "Colaboradores + líderes";
  return "Colaboradores";
}

export function pluralizeFilial(count: number, suffix: "" | " selecionada" | " coberta" = "") {
  const suffixPlural = suffix ? `${suffix}s` : "";
  return count === 1 ? `filial${suffix}` : `filiais${suffixPlural}`;
}
