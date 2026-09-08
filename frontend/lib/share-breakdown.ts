import { CATEGORICAL_SLOTS, NEUTRAL_SERIES } from "@/lib/chart-palette";

export type ShareInput = { label: string; value: number };

export type ShareSlice = {
  label: string;
  value: number;
  /** Participação no total, em % com uma casa. */
  share: number;
  color: string;
  /** Verdadeiro na fatia que agrega a cauda. */
  isOther: boolean;
};

export const OTHER_LABEL = "Outros";

/**
 * Teto PADRÃO de fatias nomeadas, usado por quem não passa `maxSlices` explícito (hoje: os donuts
 * de modelo de equipe e canal SGP, ambos com poucas categorias na prática). Era 5 até 2026-09-04
 * (achado real: com ~15 filiais reais, "Outros" chegava a ser a MAIOR fatia do donut, escondendo
 * mais informação do que mostrava); o donut de filial passou a pedir `maxSlices` igual ao total de
 * itens (nunca dobra em "Outros" - `overview-screen.tsx`), já que `assignSeriesColors` agora dá um
 * tom (ainda que não formalmente validado) pra cada entidade extra, em vez de cair no cinza.
 */
export const DEFAULT_MAX_SLICES = 8;

function share(value: number, total: number) {
  return total > 0 ? Math.round((value / total) * 1000) / 10 : 0;
}

/** Clareia (`amount` > 0, em direção ao branco) ou escurece (`amount` < 0, em direção ao preto)
 * uma cor hex - usado só para dar um tom distinto a mais pra cada volta na paleta categórica. */
function shade(hex: string, amount: number): string {
  const num = parseInt(hex.slice(1), 16);
  const mix = (channel: number) =>
    Math.max(0, Math.min(255, Math.round(amount >= 0 ? channel + (255 - channel) * amount : channel * (1 + amount))));
  const r = mix((num >> 16) & 0xff);
  const g = mix((num >> 8) & 0xff);
  const b = mix(num & 0xff);
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/**
 * Cor estável por ENTIDADE: os rótulos são ordenados alfabeticamente e recebem os slots nessa
 * ordem, independentemente do valor. Assim "UNI - JARU" tem a mesma cor com ou sem filtro, e
 * trocar o período não repinta quem continuou na tela. "Outros" é sempre o cinza neutro.
 *
 * Além do 8º rótulo (fim da paleta validada, `CATEGORICAL_SLOTS`), em vez de cair no cinza neutro
 * (que ficaria idêntico ao de "Outros" e indistinguível de outra entidade extra), a cor volta pro
 * início da paleta em tom mais claro; numa 3ª volta, mais escuro; e assim por diante. Pedido
 * explícito do usuário (2026-09-04, tela com ~15 filiais reais): cada filial com cor própria, não
 * agrupada. Os tons extras NÃO passaram pela validação de contraste/daltonismo de
 * `CATEGORICAL_SLOTS` (só a base passou) - mantêm o mesmo matiz da cor validada, então a
 * distinção por matiz continua, só a de luminosidade é que não tem a mesma garantia formal.
 */
export function assignSeriesColors(labels: readonly string[]): Map<string, string> {
  const ordered = Array.from(new Set(labels)).sort((a, b) => a.localeCompare(b, "pt-BR"));
  const colors = new Map<string, string>();
  ordered.forEach((label, index) => {
    const base = CATEGORICAL_SLOTS[index % CATEGORICAL_SLOTS.length];
    const lap = Math.floor(index / CATEGORICAL_SLOTS.length);
    // Ímpar clareia, par (>0) escurece - alterna pra não repetir quase a mesma cor de uma volta
    // pra outra (1ª volta clara + 2ª volta clara ficariam parecidas demais).
    const color = lap === 0 ? base : shade(base, lap % 2 === 1 ? 0.35 : -0.3);
    colors.set(label, color);
  });
  return colors;
}

/**
 * Reduz uma lista de partes a no máximo `maxSlices` fatias nomeadas + "Outros".
 *
 * Ordena por valor (maior primeiro) só para decidir QUEM fica nomeado; a cor vem de
 * `assignSeriesColors`, pela entidade, não pela posição. Valores zero ou negativos saem antes
 * de qualquer conta - não existe fatia vazia. Se a cauda tiver um único item, ele fica nomeado
 * em vez de virar um "Outros" de um só.
 */
export function foldShares(
  items: readonly ShareInput[],
  options: { maxSlices?: number; otherLabel?: string } = {},
): ShareSlice[] {
  const maxSlices = options.maxSlices ?? DEFAULT_MAX_SLICES;
  const otherLabel = options.otherLabel ?? OTHER_LABEL;
  const positive = items.filter((item) => item.value > 0);
  const total = positive.reduce((sum, item) => sum + item.value, 0);
  if (!total) return [];

  const ranked = [...positive].sort((a, b) => b.value - a.value || a.label.localeCompare(b.label, "pt-BR"));
  const keepCount = ranked.length <= maxSlices + 1 ? ranked.length : maxSlices;
  const named = ranked.slice(0, keepCount);
  const tail = ranked.slice(keepCount);
  const colors = assignSeriesColors(named.map((item) => item.label));

  const slices: ShareSlice[] = named.map((item) => ({
    label: item.label,
    value: item.value,
    share: share(item.value, total),
    color: colors.get(item.label) ?? NEUTRAL_SERIES,
    isOther: false,
  }));
  if (tail.length) {
    const tailValue = tail.reduce((sum, item) => sum + item.value, 0);
    slices.push({ label: otherLabel, value: tailValue, share: share(tailValue, total), color: NEUTRAL_SERIES, isOther: true });
  }
  return slices;
}
