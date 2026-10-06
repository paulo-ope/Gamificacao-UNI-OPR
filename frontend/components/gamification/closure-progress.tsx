import { Check, Circle, FileCheck2, FilePenLine, SearchCheck, Wallet } from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS = [
  { status: "draft", label: "Rascunho", icon: FilePenLine },
  { status: "review", label: "Conferência", icon: SearchCheck },
  { status: "approved", label: "Aprovado", icon: FileCheck2 },
  { status: "paid", label: "Pago", icon: Wallet },
];

/** Presentation only: the existing run status remains the sole source of truth. */
export function ClosureProgress({ status }: { status?: string }) {
  const current = STEPS.findIndex((step) => step.status === status);
  if (current < 0) return null;
  return (
    <ol aria-label="Etapas do fechamento" className="grid grid-cols-2 gap-2 rounded-xl border border-slate-200 bg-slate-50/70 p-2 sm:grid-cols-4">
      {STEPS.map((step, index) => {
        const active = index === current;
        const completed = index < current;
        const Icon = completed ? Check : active ? step.icon : Circle;
        return <li key={step.status} aria-current={active ? "step" : undefined} className={cn("flex items-center gap-2 rounded-lg px-3 py-2 text-xs", active ? "bg-white font-semibold text-primary shadow-sm ring-1 ring-slate-200" : completed ? "text-emerald-700" : "text-slate-500")}>
          <Icon className="h-4 w-4 shrink-0" aria-hidden="true" /><span>{step.label}</span><span className="sr-only">{completed ? ": concluída" : active ? ": etapa atual" : ": próxima etapa"}</span>
        </li>;
      })}
    </ol>
  );
}
