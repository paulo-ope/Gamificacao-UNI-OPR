import {
  CheckCircle2,
  CircleAlert,
  FileQuestion,
  type LucideIcon,
  Repeat,
  ShieldQuestion,
  XCircle
} from "lucide-react";

// Sistema de tons compartilhado entre os módulos (generaliza a fórmula border/bg/text de
// lib/operations-sla.ts). As classes precisam ser strings literais completas por tom - o JIT do
// Tailwind não enxerga classes montadas por interpolação.
export type Tone = "emerald" | "amber" | "red" | "blue" | "violet" | "slate";

const BADGE_CLASS: Record<Tone, string> = {
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
  amber: "border-amber-200 bg-amber-50 text-amber-800",
  red: "border-red-200 bg-red-50 text-red-700",
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  violet: "border-violet-200 bg-violet-50 text-violet-700",
  slate: "border-slate-200 bg-slate-50 text-slate-700"
};

const SOFT_BG_CLASS: Record<Tone, string> = {
  emerald: "bg-emerald-100 text-emerald-700",
  amber: "bg-amber-100 text-amber-700",
  red: "bg-red-100 text-red-700",
  blue: "bg-blue-100 text-blue-700",
  violet: "bg-violet-100 text-violet-700",
  slate: "bg-slate-200 text-slate-600"
};

const TEXT_CLASS: Record<Tone, string> = {
  emerald: "text-emerald-700",
  amber: "text-amber-800",
  red: "text-red-700",
  blue: "text-blue-700",
  violet: "text-violet-700",
  slate: "text-slate-950"
};

export function toneBadgeClass(tone: Tone) {
  return BADGE_CLASS[tone];
}

export function toneSoftBgClass(tone: Tone) {
  return SOFT_BG_CLASS[tone];
}

export function toneTextClass(tone: Tone) {
  return TEXT_CLASS[tone];
}

// `scoring_status` é texto livre vindo do backend - o registry cobre os valores canônicos e o
// matching por substring cobre o resto (nunca indexar o registry direto sem fallback).
export function scoringStatusTone(status: string): Tone {
  const normalized = status.toLowerCase();
  if (normalized.includes("anulada") || normalized.includes("penal") || normalized.includes("fora do prazo")) return "red";
  if (normalized.includes("sem regra")) return "amber";
  if (normalized.includes("garantia") || normalized.includes("reincid")) return "blue";
  if (normalized.includes("revis")) return "violet";
  if (normalized.includes("pontuada")) return "emerald";
  return "slate";
}

export type StatusEntry = { label: string; icon: LucideIcon; tone: Tone };

const SCORING_STATUS_REGISTRY: Record<string, StatusEntry> = {
  "O.S pontuada": { label: "O.S pontuada", icon: CheckCircle2, tone: "emerald" },
  "Anulada por reincidência": { label: "Anulada por reincidência", icon: Repeat, tone: "red" },
  "Anulada por diagnóstico": { label: "Anulada por diagnóstico", icon: XCircle, tone: "red" },
  "Anulada por SLA": { label: "Anulada por SLA", icon: XCircle, tone: "red" },
  "Sem regra": { label: "Sem regra", icon: FileQuestion, tone: "amber" },
  "Revisão manual": { label: "Revisão manual", icon: ShieldQuestion, tone: "violet" }
};

export function scoringStatusEntry(status: string): StatusEntry {
  return (
    SCORING_STATUS_REGISTRY[status] ?? {
      label: status,
      icon: CircleAlert,
      tone: scoringStatusTone(status)
    }
  );
}
