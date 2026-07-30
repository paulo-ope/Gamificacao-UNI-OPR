"use client";

import { BarChart3, CalendarDays, ClipboardList, Gauge, Inbox, ListChecks, Menu, Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

export type OperationTab = "overview" | "openings" | "sla" | "calendar" | "progress" | "details" | "teams";

const ITEMS: Array<{ value: OperationTab; label: string; description: string; icon: typeof Gauge }> = [
  { value: "overview", label: "Visão Geral", description: "Indicadores do período", icon: Gauge },
  { value: "openings", label: "Aberturas", description: "Entrada e desvios", icon: Inbox },
  { value: "progress", label: "Andamento", description: "Todo o backlog aberto", icon: ListChecks },
  { value: "sla", label: "SLA", description: "Prazos e produtividade", icon: BarChart3 },
  { value: "calendar", label: "Calendário", description: "Produção mensal", icon: CalendarDays },
  { value: "details", label: "Detalhamento", description: "Drill-through e busca", icon: ClipboardList },
  { value: "teams", label: "Config", description: "Modelos, jornadas, metas e assuntos", icon: Settings2 }
];

export function OperationsModuleSidebar({ activeTab, detailsCount, canManage, visibleTabs, onChange }: { activeTab: OperationTab; detailsCount: number; canManage: boolean; visibleTabs: OperationTab[]; onChange: (tab: OperationTab) => void }) {
  const visibleItems = ITEMS.filter((item) => visibleTabs.includes(item.value) && (item.value !== "teams" || canManage));
  return (
    <Sheet>
      <SheetTrigger asChild><Button type="button" size="icon" variant="outline" aria-label="Abrir menu do módulo"><Menu className="h-5 w-5" /></Button></SheetTrigger>
      <SheetContent className="left-0 right-auto w-[88vw] border-l-0 border-r bg-white p-0 text-slate-950 sm:max-w-sm">
        <SheetHeader className="border-slate-100"><SheetTitle className="text-slate-950">Operação Analítica</SheetTitle><SheetDescription className="text-slate-500">Navegação modular do UNI Workspace</SheetDescription></SheetHeader>
        <nav className="flex-1 space-y-1 p-3" aria-label="Navegação da Operação Analítica">
          {visibleItems.map((item) => { const Icon = item.icon; const selected = activeTab === item.value; return (
            <SheetClose asChild key={item.value}>
              <button type="button" onClick={() => onChange(item.value)} className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors", selected ? "bg-uni-royal/10 text-uni-royal" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950")}>
                <span className={cn("flex h-9 w-9 items-center justify-center rounded-lg", selected ? "bg-uni-royal text-white" : "bg-slate-100 text-slate-500")}><Icon className="h-4 w-4" /></span>
                <span className="min-w-0 flex-1"><span className="block text-sm font-semibold">{item.label}{item.value === "details" ? ` (${detailsCount})` : ""}</span><span className={cn("block text-[11px]", selected ? "text-uni-royal/70" : "text-slate-400")}>{item.description}</span></span>
              </button>
            </SheetClose>
          ); })}
        </nav>
        <div className="border-t border-slate-100 p-4 text-[11px] text-slate-400">Novos módulos podem ser adicionados a este menu sem alterar a navegação principal.</div>
      </SheetContent>
    </Sheet>
  );
}
