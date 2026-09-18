/**
 * Paleta única dos gráficos do ecossistema.
 *
 * Cor de gráfico NÃO é escolhida no olho: cada cor tem um papel (identidade de série, magnitude,
 * estado) e a paleta categórica só é legal se passar nas checagens de daltonismo e contraste.
 * Esta é a paleta de referência validada em 2026-09-03 contra o fundo branco dos nossos cards
 * (`node validate_palette.js "<8 hex>" --mode light --surface "#ffffff"` → PASS; pior par
 * adjacente sob protanopia ΔE 9,1, visão normal ΔE 19,6). Os slots 3, 4 e 5 ficam abaixo de
 * 3:1 de contraste sobre branco - por isso todo gráfico que os usa mostra rótulo direto (valor
 * ou %), nunca deixa a cor sozinha carregar o dado.
 *
 * Regras que valem para qualquer gráfico novo:
 * - séries recebem slots NA ORDEM, nunca ciclando; a 9ª série vira "Outros";
 * - a cor segue a ENTIDADE (filial, modelo, canal), nunca a posição no ranking - filtrar não
 *   pode repintar quem sobrou;
 * - texto (valor, rótulo, legenda) usa cor de texto, nunca a cor da série; a cor fica na marca.
 *
 * Os azuis da marca (`uni-royal` etc.) são cromaticamente próximos demais entre si para
 * identificar séries - ficam para a interface, não para dados.
 */
export const CATEGORICAL_SLOTS = [
  "#2a78d6", // 1 azul
  "#eb6834", // 2 laranja
  "#1baf7a", // 3 verde-água (contraste < 3:1 sobre branco: exige rótulo direto)
  "#eda100", // 4 amarelo   (idem)
  "#e87ba4", // 5 magenta   (idem)
  "#008300", // 6 verde
  "#4a3aa7", // 7 violeta
  "#e34948", // 8 vermelho
] as const;

/** Cinza neutro para "Outros" e para série de contexto - deliberadamente fora dos slots. */
export const NEUTRAL_SERIES = "#a3a29c";

/** Fundo dos cards. É também a cor do "vão" de 2px entre marcas que se tocam. */
export const CHART_SURFACE = "#ffffff";

/** Tinta de texto dos gráficos - alinhada aos tons de texto da interface (slate). */
export const CHART_INK = {
  primary: "#0f172a",
  secondary: "#475569",
  muted: "#64748b",
  gridline: "#e2e8f0",
} as const;

export type CategoricalSlot = (typeof CATEGORICAL_SLOTS)[number];

/**
 * Cores da marca UNI usadas dentro de configurações do ECharts - lá não dá pra usar classe do
 * Tailwind (é um objeto de config JS/canvas, não DOM). Mesmos valores exatos de
 * `tailwind.config.ts` e `app/globals.css` (`--uni-royal`, `--uni-turquoise`, `--uni-midnight`).
 *
 * Ficam AQUI (não em `CATEGORICAL_SLOTS`) de propósito: são cor de INTERFACE (fundo de gradiente
 * de uma única série, texto de rótulo), nunca identidade de série de dado - ver a regra acima
 * sobre os azuis da marca. (Achado da auditoria 2026-09-15: existiu um módulo separado
 * `lib/charts/chart-palette.ts` com estes mesmos valores, criado sem checar que este arquivo já
 * existia - unificado aqui para não haver duas fontes divergentes.)
 */
export const UNI_ROYAL = "#2d5fff";
export const UNI_TURQUOISE = "#27d9bf";
export const UNI_IMPACT = "#0028f3";
export const UNI_MIDNIGHT = "#010c8b";
