// Classes e cores da TV do SGP Suporte por tema. As classes do Tailwind precisam ser strings
// literais completas (o JIT não enxerga classe montada por interpolação) - por isso um mapa por tema
// em vez de `dark:`.
//
// Direção visual: a superfície escura sai do "preto rico" da marca UNI (#151f27), não de um azul
// genérico; o turquesa da marca fica como acento de INTERFACE (foco, pulso de "ao vivo"), nunca como
// cor de dado. Cor de status (verde/âmbar/vermelho) é semântica e só aparece quando o número é um
// problema ou uma confirmação real - o resto é tipografia e espaço, sem moldura colorida.
import { CATEGORICAL_SLOTS } from "@/lib/chart-palette";

export type TvTheme = "dark" | "light";
export type TvStatus = "ok" | "attention" | "critical" | "neutral";

type ThemeClasses = {
  page: string;
  card: string;
  title: string;
  value: string;
  label: string;
  muted: string;
  divider: string;
  barTrack: string;
  chip: string;
  // Botão de controle do cabeçalho: hover, foco visível e clique com resposta tátil.
  control: string;
  status: Record<TvStatus, { text: string; bar: string; dot: string }>;
};

const CONTROL_BASE =
  "inline-flex h-10 min-w-10 items-center justify-center gap-1.5 rounded-lg px-3 text-sm font-medium transition duration-150 " +
  "focus-visible:outline-none focus-visible:ring-2 active:scale-95 disabled:pointer-events-none disabled:opacity-40";

export const TV_CLASSES: Record<TvTheme, ThemeClasses> = {
  dark: {
    page: "bg-[#0d1319] text-slate-100",
    card: "bg-[#151f27] ring-1 ring-inset ring-white/[0.07]",
    title: "text-slate-50",
    value: "text-white",
    label: "text-[#a3b1c2]",
    muted: "text-[#a3b1c2]",
    divider: "border-white/10",
    barTrack: "bg-white/10",
    chip: "bg-white/[0.06] text-slate-200 ring-1 ring-inset ring-white/10",
    control: `${CONTROL_BASE} bg-white/[0.06] text-slate-200 ring-1 ring-inset ring-white/10 hover:bg-white/[0.12] focus-visible:ring-uni-turquoise`,
    status: {
      ok: { text: "text-emerald-400", bar: "bg-emerald-400", dot: "bg-emerald-400" },
      attention: { text: "text-amber-300", bar: "bg-amber-300", dot: "bg-amber-300" },
      critical: { text: "text-red-400", bar: "bg-red-400", dot: "bg-red-400" },
      neutral: { text: "text-white", bar: "bg-transparent", dot: "bg-slate-400" },
    },
  },
  light: {
    page: "bg-[#f3f5f9] text-slate-900",
    card: "bg-white ring-1 ring-inset ring-slate-900/[0.07] shadow-[0_1px_2px_rgba(15,23,42,0.05)]",
    title: "text-slate-950",
    value: "text-slate-950",
    label: "text-slate-500",
    muted: "text-slate-500",
    divider: "border-slate-200",
    barTrack: "bg-slate-200",
    chip: "bg-white text-slate-700 ring-1 ring-inset ring-slate-900/10",
    control: `${CONTROL_BASE} bg-white text-slate-700 ring-1 ring-inset ring-slate-900/10 hover:bg-slate-100 focus-visible:ring-uni-royal`,
    status: {
      ok: { text: "text-emerald-700", bar: "bg-emerald-600", dot: "bg-emerald-600" },
      attention: { text: "text-amber-700", bar: "bg-amber-600", dot: "bg-amber-600" },
      critical: { text: "text-red-600", bar: "bg-red-600", dot: "bg-red-600" },
      neutral: { text: "text-slate-950", bar: "bg-transparent", dot: "bg-slate-400" },
    },
  },
};

export const TV_CHART_INK: Record<TvTheme, { text: string; muted: string; grid: string; tooltipBg: string }> = {
  dark: { text: "#e2e8f0", muted: "#a3b1c2", grid: "#243241", tooltipBg: "#0d1319" },
  light: { text: "#0f172a", muted: "#64748b", grid: "#e2e8f0", tooltipBg: "#0f172a" },
};

// Cor de cada estado de presença. Objeto gráfico precisa de 3:1 contra o fundo do cartão (WCAG 1.4.11):
// no escuro os tons claros passam (4,0 a 8,0:1); no claro os mesmos tons ficavam em 2,2 a 3,0:1 e foram
// escurecidos (4,3 a 5,3:1). O rótulo e o número sempre acompanham - a cor nunca é a única pista.
export const PRESENCE_COLORS: Record<TvTheme, Record<string, string>> = {
  dark: { on: "#3fb27f", call: "#2a9fd6", au: "#eda100", pause: "#7a6ad8", oc: "#e34948", off: "#a3a29c", other: "#94a3b8" },
  light: { on: "#17805a", call: "#1672a8", au: "#a86f00", pause: "#6a5acd", oc: "#c93232", off: "#6b7785", other: "#6b7785" },
};

export function presenceColor(code: string, theme: TvTheme): string {
  return PRESENCE_COLORS[theme][code] ?? PRESENCE_COLORS[theme].other;
}

export const TV_SERIES = {
  today: CATEGORICAL_SLOTS[0],
  accent: CATEGORICAL_SLOTS[1],
  // Linha tracejada da média: cinza que passa 3:1 em cada fundo (o cinza único antigo ficava em 2,56:1 no claro).
  baseline: { dark: "#a3a29c", light: "#6b7785" },
} as const;
