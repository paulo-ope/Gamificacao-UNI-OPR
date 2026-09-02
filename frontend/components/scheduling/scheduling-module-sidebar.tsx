"use client";

import { BarChart3, CalendarDays, Clock3, Menu, Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

// 4 itens, não 7 (pedido do usuário 2026-08-31: "várias aba, não sei se faz sentido") - Equipe,
// Configurações e Sincronização eram tarefas de setup de baixa frequência, cada uma com item
// próprio no menu; agora são sub-seções dentro de uma única aba "Administração".
export type SchedulingTab = "painel" | "rankings" | "desempenho" | "administracao";

const ITEMS: Array<{ value: SchedulingTab; label: string; description: string; icon: typeof CalendarDays }> = [
  { value: "painel", label: "Painel", description: "Resumo do dia e calendário mensal", icon: CalendarDays },
  { value: "rankings", label: "Rankings e fila", description: "Produtividade, reagendamentos e O.S. sem agendamento", icon: BarChart3 },
  { value: "desempenho", label: "Desempenho", description: "SLA e tempo de resposta", icon: Clock3 },
  { value: "administracao", label: "Administração", description: "Equipe, configurações e sincronização", icon: Settings2 },
];

export function SchedulingModuleSidebar({
  activeTab,
  onChange,
}: {
  activeTab: SchedulingTab;
  onChange: (tab: SchedulingTab) => void;
}) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button type="button" size="icon" variant="outline" aria-label="Abrir menu do módulo">
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent className="left-0 right-auto w-[88vw] border-l-0 border-r bg-white p-0 text-slate-950 sm:max-w-sm">
        <SheetHeader className="border-slate-100">
          <SheetTitle className="text-slate-950">Agendamento</SheetTitle>
          <SheetDescription className="text-slate-500">Navegação modular do UNI Workspace</SheetDescription>
        </SheetHeader>
        <nav className="flex-1 space-y-1 p-3" aria-label="Navegação do Agendamento">
          {ITEMS.map((item) => {
            const Icon = item.icon;
            const selected = activeTab === item.value;
            return (
              <SheetClose asChild key={item.value}>
                <button
                  type="button"
                  onClick={() => onChange(item.value)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors",
                    selected ? "bg-uni-royal/10 text-uni-royal" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950",
                  )}
                >
                  <span className={cn("flex h-9 w-9 items-center justify-center rounded-lg", selected ? "bg-uni-royal text-white" : "bg-slate-100 text-slate-500")}>
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold">{item.label}</span>
                    <span className={cn("block text-[11px]", selected ? "text-uni-royal/70" : "text-slate-400")}>{item.description}</span>
                  </span>
                </button>
              </SheetClose>
            );
          })}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
