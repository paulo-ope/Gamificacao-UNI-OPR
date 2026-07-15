const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const integerFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const percentFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

export function formatNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(value);
}

export function formatInteger(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return integerFormat.format(value);
}

export function formatPoints(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "0 pts";
  return `${numberFormat.format(value)} pts`;
}

export function formatSignedPoints(value: number | null | undefined) {
  const safeValue = value ?? 0;
  if (safeValue === 0) return "0 pts";
  return `${safeValue < 0 ? "-" : "+"}${numberFormat.format(Math.abs(safeValue))} pts`;
}

export function formatAnnulledPoints(value: number | null | undefined) {
  const safeValue = Math.abs(value ?? 0);
  if (safeValue === 0) return "0 pts";
  return `${numberFormat.format(safeValue)} pts anulados`;
}

export function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return moneyFormat.format(value);
}

export function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${percentFormat.format(value)}%`;
}

export function formatHours(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const minutes = Math.round(value * 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (remainder === 0) return `${hours}h`;
  if (hours < 10) return `${hours}h${String(remainder).padStart(2, "0")}`;
  return `${numberFormat.format(value)}h`;
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC"
  }).format(new Date(value));
}
