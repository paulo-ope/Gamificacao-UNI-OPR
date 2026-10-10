"use client";

import { Check, Moon, Sun } from "lucide-react";
import { useState } from "react";

import { SIDEBAR_STYLES } from "@/components/workspace/sidebar-theme";
import { SectionCard } from "@/components/ui/section-card";
import { StatusToast } from "@/components/ui/status-toast";
import { useSidebarTheme } from "@/hooks/use-sidebar-theme";
import { cn } from "@/lib/utils";
import { saveSidebarTheme, type SidebarTheme } from "@/lib/workspace-appearance";

const OPTIONS: Array<{ value: SidebarTheme; label: string; description: string; icon: typeof Sun }> = [
  { value: "light", label: "Clara", description: "Branca, no mesmo visual da tela de acesso.", icon: Sun },
  { value: "dark", label: "Escura", description: "Azul-marinho, como era antes.", icon: Moon },
];

/** Miniatura fiel da barra lateral: usa as MESMAS classes do tema real, então nunca destoa dela. */
function SidebarPreview({ theme }: { theme: SidebarTheme }) {
  const styles = SIDEBAR_STYLES[theme];
  return (
    <div aria-hidden="true" className={cn("w-32 shrink-0 overflow-hidden rounded-lg border", styles.aside)}>
      <div className={cn("flex items-center gap-2 border-b px-2.5 py-2", styles.brand)}>
        <span className="h-4 w-4 rounded-full bg-uni-royal" />
        <span className={cn("text-[10px] font-semibold", styles.brandName)}>UNI Workspace</span>
      </div>
      <div className="space-y-1 p-2">
        <p className={cn("px-1 text-[7px] font-semibold uppercase tracking-[0.14em]", styles.groupLabel)}>Telas</p>
        <div className={cn("relative flex items-center gap-1.5 rounded-lg px-1.5 py-1", styles.itemSelected)}>
          <span className={cn("h-3.5 w-3.5 rounded", styles.iconBoxSelected)} />
          <span className="text-[9px] font-medium">Visão Geral</span>
        </div>
        {["Operação", "Gestão"].map((label) => (
          <div key={label} className={cn("relative flex items-center gap-1.5 rounded-lg px-1.5 py-1", styles.itemIdle)}>
            <span className={cn("h-3.5 w-3.5 rounded", styles.iconBoxIdle)} />
            <span className="text-[9px] font-medium">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AppearancePanel() {
  const theme = useSidebarTheme();
  const [message, setMessage] = useState<string | null>(null);

  function choose(next: SidebarTheme) {
    if (next === theme) return;
    saveSidebarTheme(next);
    setMessage(`Barra lateral ${next === "dark" ? "escura" : "clara"} aplicada neste navegador.`);
  }

  return (
    <>
      <SectionCard
        eyebrow="Personalização"
        title="Tema da barra lateral"
        subtitle="A escolha vale só para este navegador: em outro navegador ou computador, a barra volta ao tema padrão (clara)."
      >
        <fieldset className="mt-4">
          <legend className="sr-only">Tema da barra lateral</legend>
          <div className="grid gap-3 md:grid-cols-2">
            {OPTIONS.map((option) => {
              const selected = theme === option.value;
              const Icon = option.icon;
              return (
                <label
                  key={option.value}
                  className={cn(
                    "relative flex cursor-pointer items-center gap-4 rounded-2xl border bg-white p-4 transition-colors focus-within:ring-2 focus-within:ring-primary/40",
                    selected ? "border-primary ring-1 ring-primary/30" : "border-slate-200 hover:border-slate-300",
                  )}
                >
                  <input
                    type="radio"
                    name="sidebar-theme"
                    value={option.value}
                    checked={selected}
                    onChange={() => choose(option.value)}
                    className="sr-only"
                  />
                  <SidebarPreview theme={option.value} />
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                      <Icon className="h-4 w-4 text-slate-500" aria-hidden="true" />
                      {option.label}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">{option.description}</p>
                  </div>
                  {selected ? (
                    <span className="absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-white">
                      <Check className="h-3 w-3" aria-hidden="true" />
                      <span className="sr-only">Selecionado</span>
                    </span>
                  ) : null}
                </label>
              );
            })}
          </div>
        </fieldset>
      </SectionCard>
      <StatusToast message={message} onDismissMessage={() => setMessage(null)} />
    </>
  );
}
