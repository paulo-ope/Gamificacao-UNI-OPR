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
