import type { Tone } from "@/lib/tones";

export type SlaTone = "neutral" | "danger" | "warning" | "success";

export function slaTone(rate: number | null): SlaTone {
  if (rate === null) return "neutral";
  if (rate >= 80) return "success";
  if (rate >= 60) return "warning";
  return "danger";
}

export function slaBadgeClass(rate: number | null) {
  const tone = slaTone(rate);
  if (tone === "success") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (tone === "warning") return "border-amber-200 bg-amber-50 text-amber-700";
  if (tone === "danger") return "border-red-200 bg-red-50 text-red-700";
  return "border-slate-200 bg-slate-50 text-slate-500";
}

// Ponte para o sistema de tons compartilhado (`lib/tones.ts`). Existe para que nenhuma tela
// precise reescrever "verde acima de 80, vermelho abaixo de 60" numa terceira tabela de cor -
// achado real: a Visão Geral e o quadro por filial começaram a fazer exatamente isso.
export function slaSystemTone(rate: number | null): Tone {
  const tone = slaTone(rate);
  if (tone === "success") return "emerald";
  if (tone === "warning") return "amber";
  if (tone === "danger") return "red";
  return "slate";
}
