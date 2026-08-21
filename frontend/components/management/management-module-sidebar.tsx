"use client";

import { BriefcaseBusiness, ClipboardList, ListChecks, Menu, Tag } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

export type ManagementTab = "structure" | "cases" | "diagnostics" | "reasons";

const ITEMS: Array<{ value: ManagementTab; label: string; description: string; icon: typeof BriefcaseBusiness }> = [
  { value: "structure", label: "Estrutura operacional", description: "Colaboradores, supervisor e modelo de equipe", icon: BriefcaseBusiness },
  { value: "cases", label: "Casos de gestão", description: "Justificativas e decisão da matriz", icon: ListChecks },
  { value: "diagnostics", label: "Diagnóstico", description: "Ranking por motivo, colaborador e regional", icon: ClipboardList },
  { value: "reasons", label: "Motivos de justificativa", description: "Catálogo de motivos pré-cadastrados", icon: Tag },
];

// Mesmo padrão do menu hambúrguer da Operação Analítica (OperationsModuleSidebar) - pedido do
// usuário em 2026-08-21: Gestão Integrada tinha as abas soltas num <Tabs> inline, sem o mesmo
// menu lateral que o resto do workspace já usa, quebrando a consistência entre módulos.
export function ManagementModuleSidebar({
  activeTab,
  canAdminReasons,
  openCasesCount = 0,
  onChange,
}: {
  activeTab: ManagementTab;
  canAdminReasons: boolean;
  openCasesCount?: number;
  onChange: (tab: ManagementTab) => void;
}) {
  const visibleItems = ITEMS.filter((item) => item.value !== "reasons" || canAdminReasons);
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button type="button" size="icon" variant="outline" aria-label="Abrir menu do módulo">
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent className="left-0 right-auto w-[88vw] border-l-0 border-r bg-white p-0 text-slate-950 sm:max-w-sm">
        <SheetHeader className="border-slate-100">
          <SheetTitle className="text-slate-950">Gestão Integrada</SheetTitle>
          <SheetDescription className="text-slate-500">Navegação modular do UNI Workspace</SheetDescription>
        </SheetHeader>
        <nav className="flex-1 space-y-1 p-3" aria-label="Navegação de Gestão Integrada">
          {visibleItems.map((item) => {
            const Icon = item.icon;
            const selected = activeTab === item.value;
            return (
              <SheetClose asChild key={item.value}>
                <button
                  type="button"
                  onClick={() => onChange(item.value)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors",
                    selected ? "bg-uni-royal/10 text-uni-royal" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950"
                  )}
                >
                  <span className={cn("flex h-9 w-9 items-center justify-center rounded-lg", selected ? "bg-uni-royal text-white" : "bg-slate-100 text-slate-500")}>
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-sm font-semibold">
                      {item.label}
                      {item.value === "cases" && openCasesCount ? (
                        <span className="rounded-full bg-amber-100 px-1.5 text-[11px] font-semibold text-amber-700">{openCasesCount}</span>
                      ) : null}
                    </span>
                    <span className={cn("block text-[11px]", selected ? "text-uni-royal/70" : "text-slate-400")}>{item.description}</span>
                  </span>
                </button>
              </SheetClose>
            );
          })}
        </nav>
        <div className="border-t border-slate-100 p-4 text-[11px] text-slate-400">Novos módulos podem ser adicionados a este menu sem alterar a navegação principal.</div>
      </SheetContent>
    </Sheet>
  );
}
