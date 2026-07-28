const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

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
