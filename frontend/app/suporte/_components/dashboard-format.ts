import { percentChange } from "@/lib/period";
import type { SupportMacroCard, SupportMacroCardStatus } from "@/lib/types";

// Formatação dos cartões do Dashboard Suporte. Só apresentação: valor, meta e status vêm prontos do backend.

const decimal = (value: number, digits: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);

/** Tempo no formato do painel de metas do Suporte: HH:MM:SS. */
export function clock(totalSeconds: number) {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const hh = String(Math.floor(seconds / 3600)).padStart(2, "0");
  const mm = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function formatCardValue(card: Pick<SupportMacroCard, "unit">, value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  switch (card.unit) {
    case "score":
      return decimal(value, 2);
    case "seconds":
      return clock(value);
    case "percent":
      return `${decimal(value, 2)}%`;
    default:
      return new Intl.NumberFormat("pt-BR").format(Math.round(value));
  }
}

/** Variação absoluta assinada (ex.: "+0,04", "-00:00:45", "-18,09 p.p."). */
export function formatCardChange(card: Pick<SupportMacroCard, "unit" | "change">) {
  if (card.change === null) return null;
  const sign = card.change > 0 ? "+" : card.change < 0 ? "-" : "";
  const magnitude = Math.abs(card.change);
  switch (card.unit) {
    case "score":
      return `${sign}${decimal(magnitude, 2)}`;
    case "seconds":
      return `${sign}${clock(magnitude)}`;
    case "percent":
      return `${sign}${decimal(magnitude, 2)} p.p.`;
    default:
      return `${sign}${new Intl.NumberFormat("pt-BR").format(Math.round(magnitude))}`;
  }
}

/**
 * Linha "o que era antes": valor do período anterior, diferença absoluta e variação em %. Ex.: "Antes: 4,37 · -0,11 (-2,5%)".
 * Sem valor anterior (ou sem valor atual para comparar) não mostra nada, em vez de inventar uma base.
 */
export function formatPreviousLine(card: Pick<SupportMacroCard, "unit" | "value" | "previous" | "change">) {
  if (card.previous === null || card.previous === undefined) return null;
  const parts = [`Antes: ${formatCardValue(card, card.previous)}`];
  // Indicador que já é percentual (resolutividade): a variação em p.p. já aparece no próprio cartão; repeti-la
  // aqui, calculada de outro jeito, daria duas diferenças divergentes por arredondamento. Fica só o valor de antes.
  if (card.unit === "percent") return parts[0];
  // A diferença sai dos valores como aparecem na tela (arredondados), senão "4,34 contra 4,40" mostraria -0,05
  // por causa das casas que o cartão não exibe.
  const shown = (value: number) => (card.unit === "score" || card.unit === "percent" ? Math.round(value * 100) / 100 : Math.round(value));
  const absolute = formatCardChange({ unit: card.unit, change: card.value === null ? card.change : shown(card.value) - shown(card.previous) });
  const relative = percentChange(card.value, card.previous);
  if (absolute !== null && relative !== null) {
    const sign = relative > 0 ? "+" : "";
    parts.push(`${absolute} (${sign}${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(relative)}%)`);
  } else if (absolute !== null) {
    parts.push(absolute);
  }
  return parts.join(" · ");
}

export function formatCardTarget(card: Pick<SupportMacroCard, "unit" | "target" | "direction">) {
  if (card.target === null) return null;
  return `Meta ${card.direction === "min" ? "≥" : "≤"} ${formatCardValue(card, card.target)}`;
}

/** Quanto da meta foi atingido (0 a 100): maior-é-melhor = valor/meta; menor-é-melhor = meta/valor. */
export function goalProgress(card: Pick<SupportMacroCard, "value" | "target" | "direction">) {
  if (card.value === null || card.target === null || card.target <= 0) return null;
  if (card.direction === "min") return Math.min(100, (card.value / card.target) * 100);
  return card.value <= 0 ? 100 : Math.min(100, (card.target / card.value) * 100);
}

/** Aviso de cobertura das médias do OPA (TMR/TMA), que só existem para parte dos atendimentos. */
export function coverageNote(card: Pick<SupportMacroCard, "status" | "coverage">) {
  const coverage = card.coverage;
  if (!coverage || coverage.percentage === null) return null;
  const counts = `${new Intl.NumberFormat("pt-BR").format(coverage.count)} de ${new Intl.NumberFormat("pt-BR").format(coverage.total)} atendimentos com humano`;
  if (card.status === "partial") return `Dado parcial: média de ${counts} (${Math.round(coverage.percentage)}%)`;
  return coverage.percentage < 100 ? `Média de ${counts} (${Math.round(coverage.percentage)}%)` : null;
}

export function isGoodWhenUp(card: Pick<SupportMacroCard, "target" | "direction">) {
  return card.target === null ? null : card.direction === "min";
}

export const STATUS_TONE: Record<SupportMacroCardStatus, "emerald" | "amber" | "red" | "slate"> = {
  ok: "emerald",
  attention: "amber",
  critical: "red",
  partial: "slate",
  no_data: "slate",
  no_target: "slate",
};
